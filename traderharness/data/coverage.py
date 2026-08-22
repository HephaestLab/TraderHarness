"""Fast, explicit dataset coverage checks used before research runs."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from traderharness.core.calendar import TradingCalendar


class DataCoverageError(RuntimeError):
    """The canonical local data cannot safely serve the requested interval."""


class DatasetCoverage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @staticmethod
    def _max_date(path: Path, column: str) -> date | None:
        if not path.is_file():
            return None
        frame = pd.read_parquet(path, columns=[column])
        if frame.empty:
            return None
        return pd.Timestamp(frame[column].max()).date()

    def _metadata(self) -> dict[str, Any]:
        path = self.root / "metadata.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def watermark(self, dataset: str) -> date | None:
        metadata = self._metadata()
        value = (metadata.get("watermarks") or {}).get(dataset)
        if value:
            try:
                return date.fromisoformat(str(value))
            except ValueError:
                pass
        if dataset == "daily":
            return self._max_date(self.root / "daily.parquet", "date")
        if dataset == "benchmark":
            return self._max_date(self.root / "index_300.parquet", "date")
        if dataset == "valuation":
            return self._max_date(self.root / "valuation.parquet", "date")
        if dataset == "fundamentals":
            return self._max_date(self.root / "fundamentals.parquet", "pub_date")
        if dataset == "dividends":
            path = self.root / "dividends.parquet"
            if not path.is_file():
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
        if dataset == "announcements":
            return self._max_date(self.root / "announcements.parquet", "announcement_time")
        if dataset == "news":
            path = self.root / "news_cls.parquet"
            if not path.is_file():
                return None
            frame = pd.read_parquet(path, columns=["ctime"])
            return (
                datetime.fromtimestamp(int(frame["ctime"].max())).date()
                if not frame.empty
                else None
            )
        if dataset in {"5min", "1min"}:
            folder = self.root / f"{dataset}_clean"
            files = list(folder.rglob("*.parquet")) if folder.is_dir() else []
            if not files:
                return None
            parquet_glob = (folder / "**" / "*.parquet").resolve().as_posix().replace("'", "''")
            con = duckdb.connect()
            try:
                value = con.execute(
                    f"SELECT max(CAST(datetime AS DATE)) FROM read_parquet('{parquet_glob}', hive_partitioning=true)"
                ).fetchone()[0]
            finally:
                con.close()
            return pd.Timestamp(value).date() if value is not None else None
        raise ValueError(f"unknown dataset: {dataset}")

    @staticmethod
    def _target_session(end: date) -> date:
        calendar = TradingCalendar(strict=True)
        current = end
        try:
            while not calendar.is_trading_day(current):
                current = calendar.prev_trading_day(current)
        except ValueError as exc:
            raise DataCoverageError(str(exc)) from exc
        return current

    def assert_backtest_ready(
        self,
        start: date,
        end: date,
        *,
        require_minute: bool = True,
        minute_dataset: str = "5min",
    ) -> dict[str, Any]:
        if start > end:
            raise DataCoverageError("start date cannot be after end date")
        target = self._target_session(end)
        required = ["daily", "benchmark"]
        if require_minute:
            required.append(minute_dataset)
        watermarks = {name: self.watermark(name) for name in required}
        missing = [
            f"{name} watermark is {value.isoformat() if value else 'missing'}, needs {target.isoformat()}"
            for name, value in watermarks.items()
            if value is None or value < target
        ]
        if missing:
            raise DataCoverageError(
                "Dataset is not ready for this run: " + "; ".join(missing) + ". "
                f"Run `traderharness data update --end {end.isoformat()}` and then `traderharness data doctor`."
            )

        daily_path = self.root / "daily.parquet"
        dates = pd.read_parquet(daily_path, columns=["date"])
        present = {
            pd.Timestamp(value).date()
            for value in pd.to_datetime(dates["date"], errors="coerce").dropna().unique()
            if start <= pd.Timestamp(value).date() <= target
        }
        calendar = TradingCalendar(strict=True)
        expected = set(calendar.get_trading_days(start, target))
        missing_sessions = sorted(expected - present)
        if missing_sessions:
            preview = ", ".join(value.isoformat() for value in missing_sessions[:10])
            raise DataCoverageError(f"daily dataset has missing exchange sessions: {preview}")

        return {
            "ready": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "target_session": target.isoformat(),
            "watermarks": {
                name: value.isoformat() if value else None for name, value in watermarks.items()
            },
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    def status(self) -> dict[str, Any]:
        datasets = (
            "daily",
            "5min",
            "valuation",
            "fundamentals",
            "dividends",
            "announcements",
            "news",
            "benchmark",
        )
        metadata = self._metadata()
        pipeline_path = self.root / ".pipeline" / "latest.json"
        pipeline = None
        if pipeline_path.is_file():
            try:
                pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pipeline = {"status": "invalid"}
        return {
            "root": str(self.root),
            "watermarks": {
                name: (value.isoformat() if (value := self.watermark(name)) else None)
                for name in datasets
            },
            "last_incremental_update": metadata.get("last_incremental_update"),
            "pipeline": pipeline,
        }
