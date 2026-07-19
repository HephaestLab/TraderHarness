"""ParquetProvider — offline data from local parquet files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


class ParquetProvider:
    """Reads daily bars from local parquet files.

    Expected layout: {data_dir}/{stock_code}.parquet
    Each file must have columns: date, open, high, low, close, volume.

    Optional companion 5-minute bars live at ``{data_dir}_5min/{code}.parquet``.
    ``MarketData.load_all`` also auto-loads a sibling ``market_data_5min`` directory.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._cache: dict[str, pd.DataFrame] = {}
        self._5min_cache: dict[str, pd.DataFrame] = {}

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        df = self._load(stock_code)
        if df.empty:
            return df
        mask = (df["date"] >= start) & (df["date"] <= end)
        return df.loc[mask].reset_index(drop=True)

    async def get_5min_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        """Return real companion 5-minute bars; never synthesize from daily."""
        df = self._load_5min(stock_code)
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

    def _load_5min(self, stock_code: str) -> pd.DataFrame:
        if stock_code in self._5min_cache:
            return self._5min_cache[stock_code]
        candidates = [
            self._data_dir.parent / f"{self._data_dir.name}_5min" / f"{stock_code}.parquet",
            self._data_dir.parent / "market_data_5min" / f"{stock_code}.parquet",
        ]
        df = pd.DataFrame()
        for path in candidates:
            if path.is_file():
                df = pd.read_parquet(path)
                break
        if not df.empty:
            if "datetime" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                df["datetime"] = pd.to_datetime(df["datetime"])
            if "date" not in df.columns and "datetime" in df.columns:
                df["date"] = df["datetime"].dt.date
            elif "date" in df.columns and not all(isinstance(d, date) for d in df["date"].head(1)):
                df["date"] = pd.to_datetime(df["date"]).dt.date
        self._5min_cache[stock_code] = df
        return df
