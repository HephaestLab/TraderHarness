"""TencentProvider — fallback online data via Tencent Finance API."""

from __future__ import annotations

from datetime import date
from io import StringIO

import httpx
import pandas as pd


class TencentProvider:
    """Fetches daily bars from Tencent Finance (public, no auth needed)."""

    _BASE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get_daily_bars(
        self, stock_code: str, start: date, end: date
    ) -> pd.DataFrame:
        prefix = "sh" if stock_code.startswith("6") else "sz"
        symbol = f"{prefix}{stock_code}"
        params = {
            "param": f"{symbol},day,{start.isoformat()},{end.isoformat()},640,qfq",
        }
        try:
            resp = await self._client.get(self._BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return pd.DataFrame()

        klines = (
            data.get("data", {}).get(symbol, {}).get("day")
            or data.get("data", {}).get(symbol, {}).get("qfqday")
            or []
        )
        if not klines:
            return pd.DataFrame()

        rows = []
        for k in klines:
            if len(k) >= 6:
                rows.append({
                    "date": k[0],
                    "open": float(k[1]),
                    "close": float(k[2]),
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]),
                })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        mask = (df["date"] >= start) & (df["date"] <= end)
        return df.loc[mask].reset_index(drop=True)

    async def get_stock_list(self) -> list[dict]:
        return []

    async def close(self) -> None:
        await self._client.aclose()
