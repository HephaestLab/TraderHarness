"""Incremental update orchestration with injectable real-data providers."""

import json
from datetime import date

import pandas as pd
import pytest

from traderharness.data.updater import DataUpdater


class FakeDailyProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, codes, start, end):
        self.calls.append((codes, start, end))
        return pd.DataFrame(
            {
                "stock_code": ["600519"],
                "date": pd.to_datetime([start]),
                "close": [101.0],
            }
        )


class FakeAnnouncementsProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, start, end):
        self.calls.append((start, end))
        return pd.DataFrame(
            {
                "stock_code": ["600519"],
                "title": ["新公告"],
                "announcement_time": pd.to_datetime([f"{start} 08:00:00"]),
            }
        )


class FakeMin5Provider:
    def __init__(self):
        self.calls = []

    def fetch(self, codes, start, end):
        self.calls.append((codes, start, end))
        return pd.DataFrame(
            {
                "stock_code": ["600519"],
                "date": pd.to_datetime([start]),
                "datetime": [pd.Timestamp(f"{start} 09:35:00")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000.0],
                "amount": [100_000.0],
            }
        )


class FakeNewsProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, start, end):
        self.calls.append((start, end))
        timestamp = int(pd.Timestamp(f"{start} 08:00:00").timestamp())
        return pd.DataFrame(
            {
                "id": ["new"],
                "ctime": [timestamp],
                "display_time": pd.to_datetime([f"{start} 08:00:00"]),
                "content": ["快讯"],
            }
        )


class FakeValuationProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, codes, start, end):
        self.calls.append((codes, start, end))
        return pd.DataFrame(
            {
                "stock_code": ["600519"],
                "date": pd.to_datetime([start]),
                "turn": [1.2],
                "pe_ttm": [20.5],
                "pb_mrq": [8.1],
                "ps_ttm": [15.2],
                "is_st": [False],
            }
        )


def _seed_daily(root):
    pd.DataFrame(
        {
            "stock_code": ["600519"],
            "date": pd.to_datetime(["2024-03-01"]),
            "close": [100.0],
            "volume": [1000.0],
        }
    ).to_parquet(root / "daily.parquet", index=False)


def test_daily_update_starts_after_parquet_watermark(tmp_path):
    _seed_daily(tmp_path)
    provider = FakeDailyProvider()
    updater = DataUpdater(tmp_path, daily_provider=provider)

    result = updater.update(only={"daily"}, end=date(2024, 3, 5))

    assert provider.calls[0][1:] == (date(2024, 3, 2), date(2024, 3, 5))
    assert result["daily"].rows_added == 1
    assert len(pd.read_parquet(tmp_path / "daily.parquet")) == 2


def test_since_overrides_discovered_watermark(tmp_path):
    _seed_daily(tmp_path)
    provider = FakeDailyProvider()
    updater = DataUpdater(tmp_path, daily_provider=provider)

    updater.update(only={"daily"}, since=date(2024, 2, 20), end=date(2024, 3, 5))

    assert provider.calls[0][1] == date(2024, 2, 20)


def test_dry_run_does_not_fetch_or_write(tmp_path):
    _seed_daily(tmp_path)
    before = (tmp_path / "daily.parquet").read_bytes()
    provider = FakeDailyProvider()
    updater = DataUpdater(tmp_path, daily_provider=provider)

    plan = updater.update(only={"daily"}, end=date(2024, 3, 5), dry_run=True)

    assert provider.calls == []
    assert plan["daily"].start == date(2024, 3, 2)
    assert (tmp_path / "daily.parquet").read_bytes() == before


def test_announcement_update_uses_announcement_watermark(tmp_path):
    pd.DataFrame(
        {
            "stock_code": ["600519"],
            "title": ["旧公告"],
            "announcement_time": pd.to_datetime(["2024-03-03 08:00:00"]),
        }
    ).to_parquet(tmp_path / "announcements.parquet", index=False)
    provider = FakeAnnouncementsProvider()
    updater = DataUpdater(tmp_path, announcements_provider=provider)

    result = updater.update(only={"announcements"}, end=date(2024, 3, 5))

    assert provider.calls == [(date(2024, 3, 4), date(2024, 3, 5))]
    assert result["announcements"].rows_added == 1


def test_valuation_update_uses_its_own_watermark(tmp_path):
    _seed_daily(tmp_path)
    pd.DataFrame(
        {
            "stock_code": ["600519"],
            "date": pd.to_datetime(["2024-03-02"]),
            "turn": [1.0],
            "pe_ttm": [20.0],
            "pb_mrq": [8.0],
            "ps_ttm": [15.0],
            "is_st": [False],
        }
    ).to_parquet(tmp_path / "valuation.parquet", index=False)
    provider = FakeValuationProvider()
    updater = DataUpdater(tmp_path, valuation_provider=provider)

    result = updater.update(only={"valuation"}, end=date(2024, 3, 5))

    assert provider.calls[0][1:] == (date(2024, 3, 3), date(2024, 3, 5))
    assert result["valuation"].rows_added == 1


def test_min5_and_news_use_their_canonical_watermarks(tmp_path):
    _seed_daily(tmp_path)
    daily = pd.read_parquet(tmp_path / "daily.parquet")
    pd.concat(
        [
            daily,
            pd.DataFrame(
                {
                    "stock_code": ["600519"],
                    "date": pd.to_datetime(["2024-03-05"]),
                    "close": [101.0],
                    "volume": [1000.0],
                }
            ),
        ],
        ignore_index=True,
    ).to_parquet(tmp_path / "daily.parquet", index=False)
    year_dir = tmp_path / "5min_clean" / "year=2024"
    year_dir.mkdir(parents=True)
    FakeMin5Provider().fetch(["600519"], date(2024, 3, 1), date(2024, 3, 1)).to_parquet(
        year_dir / "part.parquet",
        index=False,
    )
    pd.DataFrame(
        {
            "id": ["old"],
            "ctime": [int(pd.Timestamp("2024-03-02 08:00:00").timestamp())],
            "display_time": pd.to_datetime(["2024-03-02 08:00:00"]),
            "content": ["旧快讯"],
        }
    ).to_parquet(tmp_path / "news_cls.parquet", index=False)
    min5 = FakeMin5Provider()
    news = FakeNewsProvider()
    updater = DataUpdater(tmp_path, min5_provider=min5, news_provider=news)

    result = updater.update(only={"5min", "news"}, end=date(2024, 3, 5))

    assert min5.calls[0][1] == date(2024, 3, 2)
    assert news.calls[0][0] == date(2024, 3, 3)
    assert result["5min"].rows_added == 1
    assert result["news"].rows_added == 1


def test_min5_watermark_uses_oldest_active_stock_not_global_max(tmp_path):
    pd.DataFrame(
        {
            "stock_code": ["600519", "000001", "600519", "000001"],
            "date": pd.to_datetime(
                ["2024-03-01", "2024-03-01", "2024-03-05", "2024-03-05"]
            ),
            "close": [100.0, 10.0, 101.0, 10.5],
            "volume": [1000.0, 1000.0, 1000.0, 1000.0],
        }
    ).to_parquet(tmp_path / "daily.parquet", index=False)
    year_dir = tmp_path / "5min_clean" / "year=2024"
    year_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "stock_code": ["600519", "000001"],
            "date": pd.to_datetime(["2024-03-05", "2024-03-01"]),
            "datetime": pd.to_datetime(["2024-03-05 15:00", "2024-03-01 15:00"]),
            "open": [100.0, 10.0],
            "high": [101.0, 10.5],
            "low": [99.0, 9.5],
            "close": [100.0, 10.0],
            "volume": [1000.0, 1000.0],
            "amount": [100_000.0, 10_000.0],
        }
    ).to_parquet(year_dir / "part.parquet", index=False)
    class CompleteMinuteProvider(FakeMin5Provider):
        def fetch(self, codes, start, end):
            self.calls.append((codes, start, end))
            rows = []
            for code in codes:
                rows.append(
                    {
                        "stock_code": code,
                        "date": pd.Timestamp(start),
                        "datetime": pd.Timestamp(f"{start} 09:35:00"),
                        "open": 10.0,
                        "high": 10.1,
                        "low": 9.9,
                        "close": 10.0,
                        "volume": 1000.0,
                        "amount": 10_000.0,
                    }
                )
            return pd.DataFrame(rows)

    provider = CompleteMinuteProvider()
    updater = DataUpdater(tmp_path, min5_provider=provider)

    updater.update(only={"5min"}, end=date(2024, 3, 5))

    assert provider.calls[0][1] == date(2024, 3, 2)


def test_min5_fetches_only_codes_with_trades_in_update_window(tmp_path):
    pd.DataFrame(
        {
            "stock_code": ["600519", "000001", "000001"],
            "date": pd.to_datetime(["2024-03-02", "2024-03-01", "2024-03-02"]),
            "close": [100.0, 10.0, 10.0],
            "volume": [1000.0, 1000.0, 0.0],
        }
    ).to_parquet(tmp_path / "daily.parquet", index=False)
    provider = FakeMin5Provider()
    updater = DataUpdater(tmp_path, min5_provider=provider)

    updater.update(
        only={"5min"},
        since=date(2024, 3, 2),
        end=date(2024, 3, 2),
    )

    assert provider.calls[0][0] == ["600519"]


def test_daily_is_merged_before_minute_universe_is_discovered(tmp_path):
    """A newly listed/active code must be visible to the minute update."""
    _seed_daily(tmp_path)

    class NewDailyProvider:
        def fetch(self, codes, start, end):
            return pd.DataFrame(
                {
                    "stock_code": ["300750"],
                    "date": pd.to_datetime([end]),
                    "close": [200.0],
                    "volume": [10_000.0],
                }
            )

    class NewMinuteProvider(FakeMin5Provider):
        def fetch(self, codes, start, end):
            self.calls.append((codes, start, end))
            frame = super().fetch(codes, start, end)
            frame["stock_code"] = codes[0]
            return frame

    minute = NewMinuteProvider()
    updater = DataUpdater(
        tmp_path,
        daily_provider=NewDailyProvider(),
        min5_provider=minute,
    )

    updater.update(
        only={"daily", "5min"},
        since=date(2024, 3, 5),
        end=date(2024, 3, 5),
    )

    assert minute.calls[0][0] == ["300750"]


def test_active_minute_universe_cannot_succeed_with_an_empty_delta(tmp_path):
    _seed_daily(tmp_path)

    class EmptyMinuteProvider:
        def fetch(self, codes, start, end):
            assert codes == ["600519"]
            return pd.DataFrame()

    updater = DataUpdater(tmp_path, min5_provider=EmptyMinuteProvider())

    import pytest

    with pytest.raises(RuntimeError, match="5min provider returned no bars"):
        updater.update(
            only={"5min"},
            since=date(2024, 3, 1),
            end=date(2024, 3, 1),
        )


def test_minute_update_refuses_a_window_not_yet_covered_by_daily(tmp_path):
    _seed_daily(tmp_path)
    updater = DataUpdater(tmp_path, min5_provider=FakeMin5Provider())

    with pytest.raises(RuntimeError, match="daily must be complete before 5min discovery"):
        updater.update(
            only={"5min"},
            since=date(2024, 3, 2),
            end=date(2024, 3, 5),
        )


def test_failed_pipeline_checkpoint_is_persisted_for_safe_resume(tmp_path):
    _seed_daily(tmp_path)

    class FailingProvider:
        def fetch(self, codes, start, end):
            raise RuntimeError("upstream blocked")

    updater = DataUpdater(tmp_path, daily_provider=FailingProvider())

    with pytest.raises(RuntimeError, match="upstream blocked"):
        updater.update(only={"daily"}, end=date(2024, 3, 5))

    state = json.loads((tmp_path / ".pipeline" / "latest.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["datasets"]["daily"]["status"] == "failed"
    assert state["datasets"]["daily"]["error"] == "upstream blocked"
