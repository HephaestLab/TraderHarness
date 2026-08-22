from datetime import date, datetime

import pandas as pd

from traderharness.core.paper_runner import (
    PaperRunConfig,
    PaperTradingRunner,
    aggregate_one_minute_to_five,
)


def test_aggregate_one_minute_to_five_only_publishes_completed_buckets():
    minutes = pd.date_range("2026-08-21 09:31:00", periods=7, freq="min")
    frame = pd.DataFrame(
        {
            "stock_code": ["600519"] * len(minutes),
            "date": minutes.normalize(),
            "datetime": minutes,
            "open": [10, 11, 12, 13, 14, 15, 16],
            "high": [11, 12, 13, 14, 15, 16, 17],
            "low": [9, 10, 11, 12, 13, 14, 15],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5],
            "volume": [100] * len(minutes),
            "amount": [1000] * len(minutes),
        }
    )

    result = aggregate_one_minute_to_five(frame, datetime(2026, 8, 21, 9, 37))

    assert result["datetime"].tolist() == [pd.Timestamp("2026-08-21 09:35:00")]
    bar = result.iloc[0]
    assert bar["open"] == 10
    assert bar["high"] == 15
    assert bar["low"] == 9
    assert bar["close"] == 14.5
    assert bar["volume"] == 500


def test_aggregate_one_minute_to_five_keeps_lunch_sessions_separate():
    times = pd.to_datetime(["2026-08-21 11:30:00", "2026-08-21 13:01:00"])
    frame = pd.DataFrame(
        {
            "stock_code": ["600519", "600519"],
            "date": times.normalize(),
            "datetime": times,
            "open": [10, 20],
            "high": [11, 21],
            "low": [9, 19],
            "close": [10.5, 20.5],
            "volume": [100, 200],
            "amount": [1000, 4000],
        }
    )

    result = aggregate_one_minute_to_five(frame, datetime(2026, 8, 21, 13, 5))

    assert result["datetime"].tolist() == [
        pd.Timestamp("2026-08-21 11:30:00"),
        pd.Timestamp("2026-08-21 13:05:00"),
    ]


def test_cancelled_runner_finishes_without_misclassifying_as_failure(tmp_path):
    runner = PaperTradingRunner(
        PaperRunConfig(
            session_id="cancel-test",
            agent={},
            session_date=date(2026, 8, 21),
            dataset_root=tmp_path,
        )
    )

    async def interrupted():
        raise RuntimeError("cooperative stop")

    runner._async_run = interrupted
    runner.stop()
    runner._run()

    events = runner.feed.drain(max_events=10)
    assert runner.error is None
    assert [event.type for event in events] == ["paper_clock", "run_end"]
    assert events[-1].data["cancelled"] is True
