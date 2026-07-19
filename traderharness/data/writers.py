"""Idempotent atomic writers for canonical market datasets."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from traderharness.data.min5_clean import MIN5_COLUMNS, clean_min5


@dataclass(frozen=True)
class WriteResult:
    rows_before: int
    rows_after: int

    @property
    def rows_added(self) -> int:
        return self.rows_after - self.rows_before


class TableWriter:
    """Atomic read/merge/deduplicate/write for a single parquet table."""

    def __init__(self, path: str | Path, dedup_keys: Iterable[str]) -> None:
        self.path = Path(path)
        self.dedup_keys = list(dedup_keys)

    def merge(self, delta: pd.DataFrame) -> WriteResult:
        existing = pd.read_parquet(self.path) if self.path.exists() else pd.DataFrame()
        rows_before = len(existing)
        combined = pd.concat([existing, delta], ignore_index=True)
        if not combined.empty:
            combined = combined.drop_duplicates(self.dedup_keys, keep="last")
            combined = combined.sort_values(self.dedup_keys).reset_index(drop=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        combined.to_parquet(temporary, index=False, compression="zstd")
        temporary.replace(self.path)
        return WriteResult(rows_before, len(combined))


class DailyWriter(TableWriter):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path, ["stock_code", "date"])


class Min5PartitionWriter:
    """Year-local DuckDB rebuild with global (stock_code, datetime) dedup."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @staticmethod
    def _sql_path(path: Path) -> str:
        return path.resolve().as_posix().replace("'", "''")

    def merge(self, delta: pd.DataFrame) -> WriteResult:
        cleaned = clean_min5(delta)
        if cleaned.empty:
            return WriteResult(0, 0)

        self.root.mkdir(parents=True, exist_ok=True)
        staging_file = self.root.parent / f".min5-delta-{uuid.uuid4().hex}.parquet"
        cleaned.to_parquet(staging_file, index=False, compression="zstd")

        rows_before_total = 0
        rows_after_total = 0
        try:
            for year in sorted(cleaned["year"].unique()):
                before, after = self._rebuild_year(int(year), staging_file)
                rows_before_total += before
                rows_after_total += after
        finally:
            staging_file.unlink(missing_ok=True)
        return WriteResult(rows_before_total, rows_after_total)

    def _rebuild_year(self, year: int, staging_file: Path) -> tuple[int, int]:
        target = self.root / f"year={year}"
        temporary = self.root / f".year={year}-{uuid.uuid4().hex}"
        backup = self.root / f".year={year}-backup-{uuid.uuid4().hex}"
        temporary.mkdir(parents=True)

        con = duckdb.connect()
        try:
            delta_path = self._sql_path(staging_file)
            columns = ", ".join(MIN5_COLUMNS)
            if target.exists() and any(target.glob("*.parquet")):
                existing_glob = self._sql_path(target / "*.parquet")
                rows_before = con.execute(
                    f"SELECT count(*) FROM read_parquet('{existing_glob}')"
                ).fetchone()[0]
                sources = (
                    f"SELECT {columns}, 0 AS _priority "
                    f"FROM read_parquet('{existing_glob}') "
                    "UNION ALL "
                    f"SELECT {columns}, 1 AS _priority "
                    f"FROM read_parquet('{delta_path}') WHERE year = {year}"
                )
            else:
                rows_before = 0
                sources = (
                    f"SELECT {columns}, 1 AS _priority "
                    f"FROM read_parquet('{delta_path}') WHERE year = {year}"
                )

            output = self._sql_path(temporary / "part.parquet")
            con.execute(
                f"""
                COPY (
                    SELECT {columns}
                    FROM ({sources})
                    QUALIFY row_number() OVER (
                        PARTITION BY stock_code, datetime
                        ORDER BY _priority DESC, volume DESC
                    ) = 1
                ) TO '{output}' (FORMAT parquet, COMPRESSION zstd)
                """
            )
            rows_after = con.execute(f"SELECT count(*) FROM read_parquet('{output}')").fetchone()[0]
        finally:
            con.close()

        try:
            if target.exists():
                target.rename(backup)
            temporary.rename(target)
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if target.exists() and backup.exists():
                shutil.rmtree(target)
            if backup.exists():
                backup.rename(target)
            raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return int(rows_before), int(rows_after)
