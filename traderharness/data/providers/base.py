"""Base data provider protocol."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class DataProvider(Protocol):
    """Protocol for market data providers."""

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        """Fetch daily OHLCV bars. Returns DataFrame with columns:
        date, open, high, low, close, volume.
        """
        ...

    async def get_stock_list(self) -> list[dict]:
        """Return available stocks: [{code, name, market, industry}]."""
        ...
