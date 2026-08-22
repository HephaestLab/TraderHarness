"""Incremental dataset update orchestration.

Providers perform network I/O; writers own canonical merge/dedup/atomic-swap
semantics. Both are injectable so orchestration is testable without replacing
the required real-data release validation.
"""

from __future__ import annotations

import json
import uuid
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
        "fundamentals",
        "dividends",
        "announcements",
        "news",
        "benchmark",
    }
    # Dependencies are deliberate: the minute universe for a new window is
    # discovered from the freshly merged positive-volume daily bars.
    UPDATE_ORDER = (
        "daily",
        "benchmark",
        "valuation",
        "fundamentals",
        "dividends",
        "5min",
        "announcements",
        "news",
    )

    def __init__(
        self,
        dataset_dir: str | Path,
        *,
        daily_provider=None,
        min5_provider=None,
        valuation_provider=None,
        fundamentals_provider=None,
        dividends_provider=None,
        announcements_provider=None,
        news_provider=None,
        benchmark_provider=None,
    ) -> None:
        self.root = Path(dataset_dir)
        self.providers = {
            "daily": daily_provider,
            "5min": min5_provider,
            "valuation": valuation_provider,
            "fundamentals": fundamentals_provider,
            "dividends": dividends_provider,
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

        ordered = [name for name in self.UPDATE_ORDER if name in selected]
        plans = {name: UpdatePlan(name, since or self._next_date(name), end) for name in ordered}
        if dry_run:
            return plans

        run_id = uuid.uuid4().hex
        state: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "requested_end": end.isoformat(),
            "datasets": {
                name: {
                    "status": "pending",
                    "start": plan.start.isoformat(),
                    "end": plan.end.isoformat(),
                }
                for name, plan in plans.items()
            },
        }
        self._write_pipeline_state(state)
        results: dict[str, Any] = {}
        try:
            for name, plan in plans.items():
                dataset_state = state["datasets"][name]
                if plan.start > plan.end:
                    results[name] = UpdatePlan(name, plan.start, plan.end)
                    dataset_state["status"] = "up_to_date"
                    self._write_pipeline_state(state)
                    continue
                provider = self.providers[name]
                if provider is None:
                    raise RuntimeError(f"No provider configured for {name}")
                dataset_state["status"] = "fetching"
                self._write_pipeline_state(state)
                try:
                    if name == "5min":
                        from traderharness.data.coverage import DatasetCoverage

                        target_session = DatasetCoverage._target_session(plan.end)
                        daily_watermark = self._watermark("daily")
                        if daily_watermark is None or daily_watermark < target_session:
                            raise RuntimeError(
                                "daily must be complete before 5min discovery: "
                                f"daily watermark is {daily_watermark or 'missing'}, "
                                f"needs {target_session}. Include daily in --only or update it first."
                            )
                        codes = self._stock_codes_with_trades(plan.start, plan.end)
                        delta = provider.fetch(codes, plan.start, plan.end)
                        if codes and delta.empty:
                            raise RuntimeError(
                                "5min provider returned no bars for "
                                f"{len(codes)} active codes in {plan.start}..{plan.end}"
                            )
                        if codes and "stock_code" in delta.columns:
                            returned = set(delta["stock_code"].astype(str).str.zfill(6))
                            missing_codes = sorted(set(codes) - returned)
                            if missing_codes:
                                preview = ", ".join(missing_codes[:10])
                                raise RuntimeError(
                                    "5min provider omitted active codes: "
                                    f"{preview} ({len(missing_codes)} total)"
                                )
                    elif name in {"daily", "valuation", "fundamentals", "dividends"}:
                        codes = self._stock_codes()
                        delta = provider.fetch(codes, plan.start, plan.end)
                    else:
                        delta = provider.fetch(plan.start, plan.end)
                    write_result = self._writer(name).merge(delta)
                except Exception as exc:
                    dataset_state["status"] = "failed"
                    dataset_state["error"] = str(exc)
                    state["status"] = "failed"
                    state["failed_at"] = datetime.now().isoformat(timespec="seconds")
                    self._write_pipeline_state(state)
                    raise
                results[name] = write_result
                dataset_state.update(
                    {
                        "status": "complete",
                        "rows_before": write_result.rows_before,
                        "rows_after": write_result.rows_after,
                        "rows_added": write_result.rows_added,
                        "provider_metrics": self._provider_metrics(provider),
                    }
                )
                self._write_pipeline_state(state)
            state["status"] = "complete"
            state["completed_at"] = datetime.now().isoformat(timespec="seconds")
            self._write_pipeline_state(state)
        finally:
            self._refresh_metadata(pipeline_state=state)
        return results

    @staticmethod
    def _provider_metrics(provider: Any) -> dict[str, Any]:
        metrics = getattr(provider, "metrics", None)
        if isinstance(metrics, dict):
            return dict(metrics)
        gate = getattr(provider, "request_gate", None) or getattr(provider, "_gate", None)
        stats = getattr(gate, "stats", None)
        return dict(stats) if isinstance(stats, dict) else {}

    def _write_pipeline_state(self, state: dict[str, Any]) -> None:
        folder = self.root / ".pipeline"
        folder.mkdir(parents=True, exist_ok=True)
        latest = folder / "latest.json"
        temporary = latest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(latest)
        run_path = folder / f"{state['run_id']}.json"
        run_temporary = run_path.with_suffix(".json.tmp")
        run_temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        run_temporary.replace(run_path)

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
        if name == "fundamentals":
            return self._max_parquet_date(self.root / "fundamentals.parquet", "pub_date")
        if name == "dividends":
            path = self.root / "dividends.parquet"
            if not path.exists():
                return None
            frame = pd.read_parquet(path, columns=["ann_date", "ex_date"])
            values = pd.concat(
                [
                    pd.to_datetime(frame["ann_date"], errors="coerce"),
                    pd.to_datetime(frame["ex_date"], errors="coerce"),
                ],
                ignore_index=True,
            ).dropna()
            return values.max().date() if not values.empty else None
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

    def _stock_codes_with_trades(self, start: date, end: date) -> list[str]:
        """Return only stocks with positive-volume daily bars in the update window."""
        path = self.root / "daily.parquet"
        if not path.exists():
            raise FileNotFoundError("daily.parquet is required to determine the stock universe")
        frame = pd.read_parquet(path, columns=["stock_code", "date", "volume"])
        dates = pd.to_datetime(frame["date"]).dt.date
        volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        active = frame[(dates >= start) & (dates <= end) & (volume > 0)]
        return sorted(active["stock_code"].astype(str).str.zfill(6).unique())

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
        if name == "fundamentals":
            return TableWriter(
                self.root / "fundamentals.parquet",
                ["stock_code", "pub_date", "stat_date"],
            )
        if name == "dividends":
            return TableWriter(
                self.root / "dividends.parquet",
                ["stock_code", "ann_date", "ex_date"],
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

    def _refresh_metadata(self, *, pipeline_state: dict[str, Any] | None = None) -> None:
        path = self.root / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        attempted_at = datetime.now().isoformat(timespec="seconds")
        metadata["last_incremental_attempt"] = attempted_at
        if pipeline_state is None or pipeline_state.get("status") == "complete":
            metadata["last_incremental_update"] = attempted_at
        watermarks = {}
        for name in sorted(self.DATASETS):
            value = self._watermark(name)
            watermarks[name] = value.isoformat() if value else None
        metadata["watermarks"] = watermarks
        daily_path = self.root / "daily.parquet"
        if daily_path.is_file():
            daily_dates = pd.read_parquet(daily_path, columns=["date"])
            if not daily_dates.empty:
                daily_summary = metadata.setdefault("daily", {})
                daily_summary["date_range"] = [
                    pd.Timestamp(daily_dates["date"].min()).date().isoformat(),
                    pd.Timestamp(daily_dates["date"].max()).date().isoformat(),
                ]
                daily_summary["refreshed_at"] = attempted_at
        if pipeline_state is not None:
            metadata["pipeline"] = {
                "run_id": pipeline_state.get("run_id"),
                "status": pipeline_state.get("status"),
                "requested_end": pipeline_state.get("requested_end"),
            }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
