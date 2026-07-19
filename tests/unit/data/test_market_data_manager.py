"""Canonical market-data loading contract."""

from datetime import date

import pandas as pd
import pytest

from traderharness.data.market_data_manager import MarketDataManager


def _bars(day: str = "2024-03-04") -> pd.DataFrame:
    ts = pd.Timestamp(f"{day} 09:35:00")
    return pd.DataFrame(
        {
            "stock_code": ["600519"],
            "date": [pd.Timestamp(day)],
            "datetime": [ts],
            "open": [1800.0],
            "high": [1810.0],
            "low": [1790.0],
            "close": [1805.0],
            "volume": [1000.0],
            "amount": [1_805_000.0],
        }
    )


@pytest.mark.parametrize("legacy_name", ["5min.parquet", "5min_chunks/part.parquet"])
def test_legacy_5min_sources_are_not_accepted(tmp_path, legacy_name):
    path = tmp_path / legacy_name
    path.parent.mkdir(parents=True, exist_ok=True)
    _bars().to_parquet(path, index=False)
    manager = MarketDataManager(tmp_path)

    assert manager.has_5min_cache() is False
    with pytest.raises(FileNotFoundError, match="data download --full"):
        manager.load_5min()


def test_loads_only_canonical_partitioned_5min_dataset(tmp_path):
    year_dir = tmp_path / "5min_clean" / "year=2024"
    year_dir.mkdir(parents=True)
    _bars().to_parquet(year_dir / "part.parquet", index=False)
    manager = MarketDataManager(tmp_path)

    loaded = manager.load_5min(date(2024, 3, 1), date(2024, 3, 31))

    assert len(loaded) == 1
    assert loaded.iloc[0]["stock_code"] == "600519"
    assert loaded.iloc[0]["date"] == date(2024, 3, 4)
    assert "year" not in loaded.columns


def test_canonical_range_filter_excludes_other_years(tmp_path):
    for year, day in ((2023, "2023-12-29"), (2024, "2024-01-02")):
        year_dir = tmp_path / "5min_clean" / f"year={year}"
        year_dir.mkdir(parents=True)
        _bars(day).to_parquet(year_dir / "part.parquet", index=False)
    manager = MarketDataManager(tmp_path)

    loaded = manager.load_5min(date(2024, 1, 1), date(2024, 12, 31))

    assert loaded["date"].tolist() == [date(2024, 1, 2)]


def test_load_daily_for_codes_filters_to_requested_stocks(tmp_path):
    frame = pd.concat(
        [
            pd.DataFrame(
                {
                    "stock_code": ["600519"] * 2,
                    "date": [pd.Timestamp("2024-03-11"), pd.Timestamp("2024-03-12")],
                    "open": [1800.0, 1805.0],
                    "high": [1810.0, 1815.0],
                    "low": [1790.0, 1795.0],
                    "close": [1805.0, 1810.0],
                    "volume": [1000.0, 1100.0],
                }
            ),
            pd.DataFrame(
                {
                    "stock_code": ["000777"],
                    "date": [pd.Timestamp("2024-03-12")],
                    "open": [9.8],
                    "high": [10.1],
                    "low": [9.7],
                    "close": [10.0],
                    "volume": [1200.0],
                }
            ),
        ],
        ignore_index=True,
    )
    frame.to_parquet(tmp_path / "daily.parquet", index=False)
    manager = MarketDataManager(tmp_path)

    loaded = manager.load_daily_for_codes(["000777"])

    assert loaded["stock_code"].unique().tolist() == ["000777"]
    assert loaded.iloc[0]["date"] == date(2024, 3, 12)


def test_load_daily_for_codes_empty_input_returns_empty_frame(tmp_path):
    manager = MarketDataManager(tmp_path)
    assert manager.load_daily_for_codes([]).empty


def test_load_daily_for_codes_without_cache_raises(tmp_path):
    manager = MarketDataManager(tmp_path)
    with pytest.raises(FileNotFoundError, match="data download --full"):
        manager.load_daily_for_codes(["000777"])


def test_missing_daily_never_triggers_network_fetch(tmp_path, monkeypatch):
    manager = MarketDataManager(tmp_path)
    called = False

    def unexpected_fetch():
        nonlocal called
        called = True

    monkeypatch.setattr(manager, "fetch_daily", unexpected_fetch)

    with pytest.raises(FileNotFoundError, match="data download --full"):
        manager.load_daily()
    assert called is False
