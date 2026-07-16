"""Benchmark data — CSI 300 index for comparison."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

from traderharness.paths import dataset_dir

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
        logger.warning("index_300.parquet not found, trying to generate from daily data")
        return _generate_from_daily(start_date, end_date, initial_cash, data_dir)

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


def _generate_from_daily(
    start_date: date,
    end_date: date,
    initial_cash: Decimal,
    data_dir: Path,
) -> list[tuple[date, Decimal]]:
    """Fallback: generate equal-weight market index from daily.parquet."""
    daily_path = data_dir / "daily.parquet"
    if not daily_path.exists():
        return []

    df = pd.read_parquet(daily_path)
    if "date" in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = df["date"].dt.date
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date

    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

    # Calculate daily market return (equal-weight average)
    daily_returns = df.groupby("date").apply(
        lambda g: g["close"].pct_change().mean() if len(g) > 1 else 0.0
    ).sort_index()

    if daily_returns.empty:
        return []

    curve = []
    value = float(initial_cash)
    for d, ret in daily_returns.items():
        if pd.notna(ret) and ret != 0:
            value *= (1 + ret)
        curve.append((d, Decimal(str(round(value, 2)))))

    return curve
