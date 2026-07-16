"""SQLite 24h cache layer for market data."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd


class DataCache:
    """SQLite-based cache with 24h TTL for daily bars."""

    _TTL_SECONDS = 86400  # 24 hours

    def __init__(self, cache_path: str | Path = ".cache/finharness.db") -> None:
        self._path = Path(cache_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_bars (
                stock_code TEXT,
                start_date TEXT,
                end_date TEXT,
                data TEXT,
                cached_at REAL,
                PRIMARY KEY (stock_code, start_date, end_date)
            )
        """)
        self._conn.commit()

    def get(self, stock_code: str, start: date, end: date) -> pd.DataFrame | None:
        cur = self._conn.execute(
            "SELECT data, cached_at FROM daily_bars WHERE stock_code=? AND start_date=? AND end_date=?",
            (stock_code, start.isoformat(), end.isoformat()),
        )
        row = cur.fetchone()
        if row is None:
            return None
        data_json, cached_at = row
        if time.time() - cached_at > self._TTL_SECONDS:
            self._conn.execute(
                "DELETE FROM daily_bars WHERE stock_code=? AND start_date=? AND end_date=?",
                (stock_code, start.isoformat(), end.isoformat()),
            )
            self._conn.commit()
            return None
        records = json.loads(data_json)
        df = pd.DataFrame(records)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def put(self, stock_code: str, start: date, end: date, df: pd.DataFrame) -> None:
        if df.empty:
            return
        df_copy = df.copy()
        if "date" in df_copy.columns:
            df_copy["date"] = df_copy["date"].astype(str)
        data_json = df_copy.to_json(orient="records")
        self._conn.execute(
            "INSERT OR REPLACE INTO daily_bars (stock_code, start_date, end_date, data, cached_at) VALUES (?,?,?,?,?)",
            (stock_code, start.isoformat(), end.isoformat(), data_json, time.time()),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM daily_bars")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
