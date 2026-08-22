from datetime import date

import pandas as pd
import pytest

from traderharness.data.coverage import DataCoverageError, DatasetCoverage


def _seed_dataset(root):
    pd.DataFrame(
        {
            "stock_code": ["600519", "600519"],
            "date": pd.to_datetime(["2026-07-30", "2026-07-31"]),
            "close": [100.0, 101.0],
            "volume": [1000.0, 1000.0],
        }
    ).to_parquet(root / "daily.parquet", index=False)
    pd.DataFrame(
        {"date": pd.to_datetime(["2026-07-30", "2026-07-31"]), "close": [4000.0, 4010.0]}
    ).to_parquet(root / "index_300.parquet", index=False)


def test_backtest_gate_rejects_a_requested_session_beyond_daily_watermark(tmp_path):
    _seed_dataset(tmp_path)
    coverage = DatasetCoverage(tmp_path)

    with pytest.raises(DataCoverageError, match="daily.*2026-08-03"):
        coverage.assert_backtest_ready(date(2026, 7, 30), date(2026, 8, 3), require_minute=False)


def test_backtest_gate_accepts_a_weekend_end_after_last_complete_session(tmp_path):
    _seed_dataset(tmp_path)
    coverage = DatasetCoverage(tmp_path)

    report = coverage.assert_backtest_ready(
        date(2026, 7, 30),
        date(2026, 8, 1),
        require_minute=False,
    )

    assert report["target_session"] == "2026-07-31"
    assert report["ready"] is True
