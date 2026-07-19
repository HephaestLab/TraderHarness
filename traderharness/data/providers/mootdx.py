"""MootdxProvider — online data via mootdx library."""

from __future__ import annotations

from datetime import date

import pandas as pd


class MootdxProvider:
    """Fetches daily bars from TDX protocol (requires mootdx installed)."""

    def __init__(self) -> None:
        self._api = None

    def _ensure_api(self):
        if self._api is None:
            try:
                from mootdx.quotes import Quotes

                self._api = Quotes.factory(market="std")
            except ImportError:
                raise ImportError("mootdx not installed. Run: pip install traderharness[data]")

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        self._ensure_api()
        days = (end - start).days + 60
        df = self._api.bars(symbol=stock_code, frequency=9, offset=days)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        if "datetime" in df.columns:
            df["date"] = pd.to_datetime(df["datetime"]).dt.date
        df = df.rename(columns={"vol": "volume"})
        cols = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]]
        mask = (df["date"] >= start) & (df["date"] <= end)
        return df.loc[mask].reset_index(drop=True)

    async def get_stock_list(self) -> list[dict]:
        self._ensure_api()
        result = []
        for market in (0, 1):
            stocks = self._api.stocks(market=market)
            if stocks is not None:
                for _, row in stocks.iterrows():
                    result.append(
                        {
                            "code": row.get("code", ""),
                            "name": row.get("name", ""),
                            "market": "sz" if market == 0 else "sh",
                        }
                    )
        return result
