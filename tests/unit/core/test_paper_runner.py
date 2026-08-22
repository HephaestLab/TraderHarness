from datetime import date, datetime

import pandas as pd

from traderharness.core.events import EventBus
from traderharness.core.paper_runner import (
    PaperRunConfig,
    PaperTradingRunner,
    _AgentEventBus,
    aggregate_one_minute_to_five,
    build_market_pulse,
    select_news_broadcasts,
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
            agents=[{}],
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


def test_market_pulse_surfaces_price_move_and_volume_acceleration():
    times = pd.date_range("2026-08-21 09:31:00", periods=6, freq="min")
    frame = pd.DataFrame(
        {
            "stock_code": ["600519"] * 6,
            "datetime": times,
            "open": [10, 10.1, 10.2, 10.3, 10.4, 10.5],
            "high": [10.2, 10.3, 10.4, 10.5, 10.6, 11.2],
            "low": [9.9, 10, 10.1, 10.2, 10.3, 10.4],
            "close": [10.1, 10.2, 10.3, 10.4, 10.5, 11.1],
            "volume": [100, 100, 100, 100, 100, 500],
            "amount": [1000, 1000, 1000, 1000, 1000, 5500],
        }
    )

    pulse = build_market_pulse(
        frame,
        cutoff=datetime(2026, 8, 21, 9, 36),
        codes=["600519"],
        names={"600519": "贵州茅台"},
    )

    assert pulse["advancers"] == 1
    assert pulse["decliners"] == 0
    assert pulse["items"][0]["stock_name"] == "贵州茅台"
    assert pulse["items"][0]["change_pct"] == 11.0
    assert pulse["items"][0]["volume_ratio"] == 5.0
    assert pulse["items"][0]["importance"] == "high"


def test_news_broadcasts_prioritize_related_announcements_and_high_level_flash():
    announcements = pd.DataFrame(
        {
            "stock_code": ["600519", "000001"],
            "title": ["签署重大合同", "普通公告"],
            "announcement_time": pd.to_datetime(
                ["2026-08-21 09:42:00", "2026-08-21 09:43:00"]
            ),
        }
    )
    news = pd.DataFrame(
        {
            "id": ["flash-1", "flash-2"],
            "display_time": pd.to_datetime(
                ["2026-08-21 09:45:00", "2026-08-21 09:46:00"]
            ),
            "content": ["央行宣布重要政策安排", "市场普通快讯"],
            "level": ["A", ""],
            "tags": ["宏观", "其他"],
        }
    )

    items = select_news_broadcasts(
        news,
        announcements,
        target_codes={"600519"},
        window_start=datetime(2026, 8, 21, 9, 40),
        window_end=datetime(2026, 8, 21, 9, 50),
    )

    assert [item["kind"] for item in items[:2]] == ["announcement", "flash"]
    assert items[0]["stock_code"] == "600519"
    assert items[0]["importance"] == "high"
    assert items[1]["source_id"] == "flash-1"


def test_agent_event_bus_injects_identity_without_overwriting_explicit_fields():
    target = EventBus()
    captured = []
    target.on("tool_call", lambda **payload: captured.append(payload))
    scoped = _AgentEventBus(target, agent_id="agent-b", agent_name="Agent B")

    scoped.emit("tool_call", tool="execute_code")
    scoped.emit("tool_call", tool="place_order", agent_id="executor")

    assert captured[0]["agent_id"] == "agent-b"
    assert captured[0]["agent_name"] == "Agent B"
    assert captured[1]["agent_id"] == "executor"
