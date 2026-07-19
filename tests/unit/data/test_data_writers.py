"""Idempotent, atomic writers used by incremental data updates."""

import pandas as pd

from traderharness.data.writers import DailyWriter, Min5PartitionWriter, TableWriter


def test_daily_writer_merges_and_deduplicates_by_stock_date(tmp_path):
    path = tmp_path / "daily.parquet"
    pd.DataFrame(
        {
            "stock_code": ["600519"],
            "date": pd.to_datetime(["2024-03-01"]),
            "close": [100.0],
        }
    ).to_parquet(path, index=False)
    delta = pd.DataFrame(
        {
            "stock_code": ["600519", "600519"],
            "date": pd.to_datetime(["2024-03-01", "2024-03-04"]),
            "close": [101.0, 102.0],
        }
    )

    result = DailyWriter(path).merge(delta)
    saved = pd.read_parquet(path).sort_values("date").reset_index(drop=True)

    assert result.rows_added == 1
    assert saved["close"].tolist() == [101.0, 102.0]
    assert not path.with_suffix(".parquet.tmp").exists()


def test_generic_table_writer_is_idempotent(tmp_path):
    path = tmp_path / "announcements.parquet"
    delta = pd.DataFrame(
        {
            "stock_code": ["600519"],
            "title": ["公告"],
            "announcement_time": pd.to_datetime(["2024-03-01 08:00:00"]),
        }
    )
    writer = TableWriter(path, ["stock_code", "title", "announcement_time"])

    first = writer.merge(delta)
    second = writer.merge(delta)

    assert first.rows_added == 1
    assert second.rows_added == 0
    assert len(pd.read_parquet(path)) == 1


def _min5(day: str, close: float, raw_time: bool = False) -> pd.DataFrame:
    timestamp = pd.Timestamp(f"{day} 09:35:00")
    return pd.DataFrame(
        {
            "stock_code": ["600519"],
            "date": [pd.Timestamp(day)],
            "datetime": [timestamp.strftime("%Y%m%d%H%M%S000") if raw_time else timestamp],
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [close],
            "volume": [1000.0],
            "amount": [100_000.0],
        }
    )


def test_min5_writer_rebuilds_only_affected_year_and_deduplicates(tmp_path):
    root = tmp_path / "5min_clean"
    old_2023 = root / "year=2023"
    old_2024 = root / "year=2024"
    old_2023.mkdir(parents=True)
    old_2024.mkdir(parents=True)
    _min5("2023-12-29", 90.0).to_parquet(old_2023 / "part.parquet", index=False)
    _min5("2024-03-01", 100.0).to_parquet(old_2024 / "part.parquet", index=False)
    untouched_before = (old_2023 / "part.parquet").read_bytes()

    delta = pd.concat(
        [_min5("2024-03-01", 101.0, raw_time=True), _min5("2024-03-04", 102.0, raw_time=True)],
        ignore_index=True,
    )
    result = Min5PartitionWriter(root).merge(delta)

    saved = pd.read_parquet(root / "year=2024").sort_values("datetime")
    assert result.rows_added == 1
    assert saved["close"].tolist() == [101.0, 102.0]
    assert (root / "year=2023" / "part.parquet").read_bytes() == untouched_before
