"""Benchmark data — CSI 300 index for comparison."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from traderharness.paths import dataset_dir

logger = logging.getLogger(__name__)

DATASET_DIR = dataset_dir()


def load_csi300_curve(
    start_date: date,
    end_date: date,
    initial_cash: Decimal,
    dataset_dir: Path | None = None,
) -> list[tuple[date, Decimal]]:
    """Load CSI 300 index and normalize to initial_cash as equity curve."""
    data_dir = dataset_dir or DATASET_DIR
    index_path = data_dir / "index_300.parquet"

    if not index_path.exists():
        logger.warning(
            "index_300.parquet not found; benchmark omitted. "
            "Run `traderharness data update --only benchmark`."
        )
        return []

    df = pd.read_parquet(index_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)].sort_values("date")

    if df.empty:
        return []

    base = float(df.iloc[0]["close"])
    curve = []
    for _, row in df.iterrows():
        normalized = Decimal(str(float(initial_cash) * float(row["close"]) / base))
        curve.append((row["date"], normalized.quantize(Decimal("0.01"))))

    return curve
