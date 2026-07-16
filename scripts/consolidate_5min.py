"""Consolidate & clean the 5-minute kline chunks into a partitioned dataset.

Background
----------
The 5-year 5min backfill (BaoStock) already fetched ~248M rows / 4743 stocks
into ~/.finharness/dataset/5min_chunks/ (1432 files), but two problems remain:

1. Mixed datetime formats across chunks:
   - Format A (correct): "09:35:00"               (8 chars, parsed time)
   - Format B (raw):     "20210517093500000"      (17 chars, raw BaoStock time)
   The loader only inspected the first row to decide the format, so Format B
   rows were mis-parsed (collapsed to ~03:36), corrupting ~5.65% of bars.

2. 320 stocks (mostly ST / delisted / suspended) have daily history but no 5min
   in the chunks. The legacy single file 5min.parquet (mootdx, 2025+) still has
   their recent bars, so we union those back in.

This script normalizes BOTH datetime formats, drops out-of-session bars, unions
the 320 missing stocks from the legacy file, and writes a Hive-partitioned
(year=YYYY) dataset to ~/.finharness/dataset/5min_clean/ for fast pushdown loads.

Usage:
    cd D:\\finharness
    .venv\\Scripts\\python.exe scripts/consolidate_5min.py
"""

from __future__ import annotations

import shutil
import time
from datetime import time as dtime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads

DATASET_DIR = Path.home() / ".finharness" / "dataset"
CHUNK_DIR = DATASET_DIR / "5min_chunks"
LEGACY_FILE = DATASET_DIR / "5min.parquet"
CLEAN_DIR = DATASET_DIR / "5min_clean"

OUT_COLS = ["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]
SESSION_MORNING = (dtime(9, 30), dtime(11, 30))
SESSION_AFTERNOON = (dtime(13, 0), dtime(15, 0))
FLUSH_ROWS = 3_000_000  # flush buffer to disk once it reaches this many cleaned rows

_stats = {"raw_rows": 0, "kept_rows": 0, "dropped_session": 0, "fixed_fmt_b": 0}


def normalize_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Build a proper datetime64 column from either string format or a passthrough."""
    dt = df["datetime"]
    base_date = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    if pd.api.types.is_datetime64_any_dtype(dt):
        # Legacy file already has full timestamps.
        df["datetime"] = pd.to_datetime(dt)
        return df

    s = dt.astype(str)
    ln = s.str.len()
    is_raw = ln >= 14  # Format B "YYYYMMDDHHMMSS..." (17 chars)
    _stats["fixed_fmt_b"] += int(is_raw.sum())

    time_str = s.copy()
    time_str.loc[is_raw] = (
        s[is_raw].str[8:10] + ":" + s[is_raw].str[10:12] + ":" + s[is_raw].str[12:14]
    )
    df["datetime"] = pd.to_datetime(base_date + " " + time_str, errors="coerce")
    return df


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    _stats["raw_rows"] += len(df)
    df = normalize_datetime(df)
    df = df[df["datetime"].notna()]

    t = df["datetime"].dt.time
    in_session = (
        ((t >= SESSION_MORNING[0]) & (t <= SESSION_MORNING[1]))
        | ((t >= SESSION_AFTERNOON[0]) & (t <= SESSION_AFTERNOON[1]))
    )
    _stats["dropped_session"] += int((~in_session).sum())
    df = df[in_session]

    if "volume" in df.columns:
        df = df[df["volume"] > 0]

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["datetime"].dt.year
    for col in OUT_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[OUT_COLS + ["year"]].drop_duplicates(subset=["stock_code", "datetime"])
    _stats["kept_rows"] += len(df)
    return df


def write_batch(df: pd.DataFrame, batch_id: int) -> None:
    if df.empty:
        return
    table = pa.Table.from_pandas(df, preserve_index=False)
    pads.write_dataset(
        table,
        base_dir=str(CLEAN_DIR),
        partitioning=["year"],
        partitioning_flavor="hive",
        format="parquet",
        existing_data_behavior="overwrite_or_ignore",
        basename_template=f"part-{batch_id:04d}-{{i}}.parquet",
    )


def chunk_stock_universe() -> set[str]:
    stocks: set[str] = set()
    for c in CHUNK_DIR.glob("*.parquet"):
        stocks.update(pd.read_parquet(c, columns=["stock_code"])["stock_code"].unique().tolist())
    return stocks


def main() -> None:
    t0 = time.time()
    if CLEAN_DIR.exists():
        print(f"Removing stale {CLEAN_DIR} ...", flush=True)
        shutil.rmtree(CLEAN_DIR)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    chunks = sorted(CHUNK_DIR.glob("*.parquet"))
    print(f"Consolidating {len(chunks)} chunks, flushing every ~{FLUSH_ROWS:,} rows ...", flush=True)

    batch_id = 0
    buffer: list[pd.DataFrame] = []
    buffered_rows = 0

    def flush() -> None:
        nonlocal batch_id, buffer, buffered_rows
        if not buffer:
            return
        df = pd.concat(buffer, ignore_index=True)
        write_batch(df, batch_id)
        batch_id += 1
        buffer = []
        buffered_rows = 0
        del df

    for i, c in enumerate(chunks, 1):
        try:
            cleaned = clean_frame(pd.read_parquet(c))
        except Exception as e:  # noqa: BLE001
            print(f"  !! chunk {c.name} failed: {e}", flush=True)
            continue
        if not cleaned.empty:
            buffer.append(cleaned)
            buffered_rows += len(cleaned)
        if buffered_rows >= FLUSH_ROWS:
            flush()
        if i % 80 == 0 or i == len(chunks):
            print(
                f"  [{i}/{len(chunks)}] kept={_stats['kept_rows']:,} "
                f"dropped_session={_stats['dropped_session']:,} fixed_fmtB={_stats['fixed_fmt_b']:,} "
                f"| {time.time() - t0:.0f}s",
                flush=True,
            )
    flush()

    # --- Union: 320 stocks present in legacy file but missing from chunks ---
    if LEGACY_FILE.exists():
        chunk_stocks = chunk_stock_universe()
        legacy_stocks = set(
            pd.read_parquet(LEGACY_FILE, columns=["stock_code"])["stock_code"].unique()
        )
        missing = sorted(legacy_stocks - chunk_stocks)
        print(f"Union: {len(missing)} stocks only in legacy 5min.parquet", flush=True)
        if missing:
            legacy = pd.read_parquet(LEGACY_FILE, filters=[("stock_code", "in", missing)])
            legacy = clean_frame(legacy)
            write_batch(legacy, batch_id)
            batch_id += 1
            print(f"  union kept={len(legacy):,} rows", flush=True)

    print("\n=== Summary ===", flush=True)
    print(f"raw rows read:      {_stats['raw_rows']:,}", flush=True)
    print(f"rows kept:          {_stats['kept_rows']:,}", flush=True)
    print(f"dropped (session):  {_stats['dropped_session']:,}", flush=True)
    print(f"fixed format-B:     {_stats['fixed_fmt_b']:,}", flush=True)
    size = sum(p.stat().st_size for p in CLEAN_DIR.rglob("*.parquet")) / 1024 / 1024
    nfiles = len(list(CLEAN_DIR.rglob("*.parquet")))
    print(f"output: {CLEAN_DIR} | {nfiles} files | {size:,.0f} MB", flush=True)
    print(f"total time: {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
