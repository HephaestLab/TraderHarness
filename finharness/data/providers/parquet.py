"""ParquetProvider — offline data from local parquet files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


class ParquetProvider:
    """Reads daily bars from local parquet files.

    Expected layout: {data_dir}/{stock_code}.parquet
    Each file must have columns: date, open, high, low, close, volume.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._cache: dict[str, pd.DataFrame] = {}

    async def get_daily_bars(
        self, stock_code: str, start: date, end: date
    ) -> pd.DataFrame:
        df = self._load(stock_code)
        if df.empty:
            return df
        mask = (df["date"] >= start) & (df["date"] <= end)
        return df.loc[mask].reset_index(drop=True)

    async def get_stock_list(self) -> list[dict]:
        results = []
        if self._data_dir.exists():
            for f in self._data_dir.glob("*.parquet"):
                results.append({"code": f.stem, "name": f.stem})
        return results

    def _load(self, stock_code: str) -> pd.DataFrame:
        if stock_code in self._cache:
            return self._cache[stock_code]
        path = self._data_dir / f"{stock_code}.parquet"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(path)
        if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"]).dt.date
        elif "date" in df.columns:
            df["date"] = df["date"].dt.date
        self._cache[stock_code] = df
        return df
