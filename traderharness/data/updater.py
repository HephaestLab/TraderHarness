"""Incremental dataset update orchestration.

Providers perform network I/O; writers own canonical merge/dedup/atomic-swap
semantics. Both are injectable so orchestration is testable without replacing
the required real-data release validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from traderharness.data.writers import DailyWriter, Min5PartitionWriter, TableWriter


@dataclass(frozen=True)
class UpdatePlan:
    dataset: str
    start: date
    end: date


class DataUpdater:
    DATASETS = {
        "daily",
        "5min",
        "valuation",
        "announcements",
        "news",
        "benchmark",
    }

    def __init__(
        self,
        dataset_dir: str | Path,
        *,
        daily_provider=None,
        min5_provider=None,
        valuation_provider=None,
        announcements_provider=None,
        news_provider=None,
        benchmark_provider=None,
    ) -> None:
        self.root = Path(dataset_dir)
        self.providers = {
            "daily": daily_provider,
            "5min": min5_provider,
            "valuation": valuation_provider,
            "announcements": announcements_provider,
            "news": news_provider,
            "benchmark": benchmark_provider,
        }

    def update(
        self,
        *,
        only: set[str] | None = None,
        since: date | None = None,
        end: date | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        selected = only or set(self.DATASETS)
        unknown = selected - self.DATASETS
        if unknown:
            raise ValueError(f"Unknown datasets: {sorted(unknown)}")
        end = end or date.today()

        plans = {
            name: UpdatePlan(name, since or self._next_date(name), end) for name in sorted(selected)
        }
        if dry_run:
            return plans

        results: dict[str, Any] = {}
        for name, plan in plans.items():
            if plan.start > plan.end:
                results[name] = UpdatePlan(name, plan.start, plan.end)
                continue
            provider = self.providers[name]
            if provider is None:
                raise RuntimeError(f"No provider configured for {name}")
            if name in {"daily", "5min", "valuation"}:
                codes = self._stock_codes()
                delta = provider.fetch(codes, plan.start, plan.end)
            else:
                delta = provider.fetch(plan.start, plan.end)
            results[name] = self._writer(name).merge(delta)

        self._refresh_metadata()
        return results

    def _next_date(self, name: str) -> date:
        watermark = self._watermark(name)
        if watermark is None:
            raise FileNotFoundError(
                f"Cannot update {name}: no canonical local dataset. "
                "Run `traderharness data download --full` first or pass --since."
            )
        return watermark + timedelta(days=1)

    def _watermark(self, name: str) -> date | None:
        if name == "daily":
            return self._max_parquet_date(self.root / "daily.parquet", "date")
        if name == "benchmark":
            return self._max_parquet_date(self.root / "index_300.parquet", "date")
        if name == "valuation":
            return self._max_parquet_date(self.root / "valuation.parquet", "date")
        if name == "announcements":
            return self._max_parquet_date(
                self.root / "announcements.parquet",
                "announcement_time",
            )
        if name == "news":
            path = self.root / "news_cls.parquet"
            if not path.exists():
                return None
            frame = pd.read_parquet(path, columns=["ctime"])
            if frame.empty:
                return None
            value = frame["ctime"].max()
            return datetime.fromtimestamp(int(value)).date()
        if name == "5min":
            clean = self.root / "5min_clean"
            if not clean.exists() or not any(clean.rglob("*.parquet")):
                return None
            glob = (clean / "**" / "*.parquet").resolve().as_posix().replace("'", "''")
            daily = (self.root / "daily.parquet").resolve().as_posix().replace("'", "''")
            con = duckdb.connect()
            try:
                value = con.execute(
                    f"""
                    WITH daily_by_code AS (
                        SELECT stock_code,
                               min(CAST(date AS DATE)) AS first_date,
                               max(CAST(date AS DATE)) AS last_date
                        FROM read_parquet('{daily}')
                        WHERE try_cast(volume AS DOUBLE) > 0
                        GROUP BY stock_code
                    ),
                    market AS (
                        SELECT max(last_date) AS market_date FROM daily_by_code
                    ),
                    active AS (
                        SELECT stock_code, first_date
                        FROM daily_by_code, market
                        WHERE last_date >= market_date - INTERVAL 7 DAY
                    ),
                    bars AS (
                        SELECT stock_code, max(datetime) AS last_bar
                        FROM read_parquet('{glob}', hive_partitioning=true)
                        GROUP BY stock_code
                    )
                    SELECT min(coalesce(CAST(last_bar AS DATE), first_date))
                    FROM active
                    LEFT JOIN bars USING (stock_code)
                    """
                ).fetchone()[0]
            finally:
                con.close()
            return pd.Timestamp(value).date() if value is not None else None
        raise ValueError(name)

    @staticmethod
    def _max_parquet_date(path: Path, column: str) -> date | None:
        if not path.exists():
            return None
        frame = pd.read_parquet(path, columns=[column])
        if frame.empty:
            return None
        return pd.Timestamp(frame[column].max()).date()

    def _stock_codes(self) -> list[str]:
        path = self.root / "daily.parquet"
        if not path.exists():
            raise FileNotFoundError("daily.parquet is required to determine the stock universe")
        frame = pd.read_parquet(path, columns=["stock_code"])
        return sorted(frame["stock_code"].astype(str).str.zfill(6).unique())

    def _writer(self, name: str):
        if name == "daily":
            return DailyWriter(self.root / "daily.parquet")
        if name == "benchmark":
            return TableWriter(self.root / "index_300.parquet", ["date"])
        if name == "valuation":
            return TableWriter(
                self.root / "valuation.parquet",
                ["stock_code", "date"],
            )
        if name == "5min":
            return Min5PartitionWriter(self.root / "5min_clean")
        if name == "announcements":
            return TableWriter(
                self.root / "announcements.parquet",
                ["stock_code", "title", "announcement_time"],
            )
        if name == "news":
            return TableWriter(self.root / "news_cls.parquet", ["id"])
        raise ValueError(name)

    def _refresh_metadata(self) -> None:
        path = self.root / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        metadata["last_incremental_update"] = datetime.now().isoformat(timespec="seconds")
        watermarks = {}
        for name in sorted(self.DATASETS):
            value = self._watermark(name)
            watermarks[name] = value.isoformat() if value else None
        metadata["watermarks"] = watermarks
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
