"""CSI 300 benchmark must never silently become an equal-weight proxy."""

from datetime import date
from decimal import Decimal

import pandas as pd

from traderharness.metrics.benchmark import load_csi300_curve


def test_missing_index_returns_empty_instead_of_fake_market_proxy(tmp_path):
    pd.DataFrame(
        {
            "stock_code": ["600519", "600000"],
            "date": pd.to_datetime(["2024-03-01", "2024-03-01"]),
            "close": [100.0, 10.0],
        }
    ).to_parquet(tmp_path / "daily.parquet", index=False)

    curve = load_csi300_curve(
        date(2024, 3, 1),
        date(2024, 3, 5),
        Decimal("1000000"),
        tmp_path,
    )

    assert curve == []


def test_loads_and_normalizes_real_index_file(tmp_path):
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-03-01", "2024-03-04"]),
            "close": [3500.0, 3535.0],
        }
    ).to_parquet(tmp_path / "index_300.parquet", index=False)

    curve = load_csi300_curve(
        date(2024, 3, 1),
        date(2024, 3, 4),
        Decimal("1000000"),
        tmp_path,
    )

    assert curve[-1][1] == Decimal("1010000.00")
