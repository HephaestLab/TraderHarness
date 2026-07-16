"""
Fetch 5 years of 5-minute kline data for all A-share stocks using BaoStock.
4 parallel workers, each with independent BaoStock connection.
Stores as parquet at ~/.traderharness/dataset/5min.parquet

Expected: ~5073 stocks × 58000 bars = ~290M rows, ~2-3 GB parquet.
"""

import sys
import time
import json
from datetime import date
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "5min_full.parquet"
PROGRESS_PATH = DATASET_DIR / "5min_backfill_progress.json"

START_DATE = "2021-05-15"
END_DATE = "2026-05-15"
WORKERS = 2
FIELDS = "date,time,code,open,high,low,close,volume,amount"


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_index": 0, "total_records": 0}


def save_progress(last_index, total_records):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_index": last_index, "total_records": total_records}, f)


def get_stock_codes():
    daily_path = DATASET_DIR / "daily.parquet"
    df = pd.read_parquet(daily_path, columns=["stock_code"])
    return sorted(df["stock_code"].unique().tolist())


def code_to_baostock(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def fetch_batch(codes: list) -> pd.DataFrame:
    """Fetch 5min data for a batch of codes. Each process has its own BS connection."""
    lg = bs.login()
    if lg.error_code != "0":
        return pd.DataFrame()

    all_dfs = []
    for code in codes:
        bs_code = code_to_baostock(code)
        rs = bs.query_history_k_data_plus(
            bs_code, FIELDS,
            start_date=START_DATE, end_date=END_DATE,
            frequency="5", adjustflag="3"
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

        if rows:
            df = pd.DataFrame(rows, columns=FIELDS.split(","))
            df["stock_code"] = code
            all_dfs.append(df)

    bs.logout()

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    # Parse time: '20210517093500000' → '09:35:00'
    combined["datetime"] = combined["time"].str[8:10] + ":" + combined["time"].str[10:12] + ":" + combined["time"].str[12:14]
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined[combined["volume"] > 0]
    return combined[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]]


def main():
    progress = load_progress()
    codes = get_stock_codes()
    start_idx = progress["last_index"]
    codes = codes[start_idx:]

    print(f"Fetching 5min data: {len(codes)} stocks remaining, {WORKERS} workers", flush=True)
    print(f"Period: {START_DATE} ~ {END_DATE}", flush=True)
    print(f"Resuming from index: {start_idx}", flush=True)

    # Split into batches of 10 stocks per worker task
    batch_size = 10
    batches = [codes[i:i+batch_size] for i in range(0, len(codes), batch_size)]

    start_time = time.time()
    total_records = progress["total_records"]
    processed = 0

    chunk_dir = DATASET_DIR / "5min_chunks"
    chunk_dir.mkdir(exist_ok=True)
    chunk_id = len(list(chunk_dir.glob("*.parquet")))

    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        futures = {}
        batch_idx = 0

        for i in range(min(WORKERS * 2, len(batches))):
            future = executor.submit(fetch_batch, batches[i])
            futures[future] = i
            batch_idx = i + 1

        while futures:
            for future in as_completed(futures):
                bi = futures.pop(future)
                try:
                    df = future.result()
                    if not df.empty:
                        chunk_path = chunk_dir / f"chunk_{chunk_id:05d}.parquet"
                        df.to_parquet(chunk_path, index=False)
                        total_records += len(df)
                        chunk_id += 1
                except Exception as e:
                    print(f"  Batch {bi} error: {e}", flush=True)

                processed += batch_size
                current_idx = start_idx + processed
                elapsed = time.time() - start_time
                rate = processed / elapsed * 60 if elapsed > 0 else 0
                remaining = len(codes) - processed
                eta = remaining / rate if rate > 0 else 0

                if processed % 50 == 0:
                    print(
                        f"  [{current_idx}/{start_idx + len(codes)}] Records: {total_records:,} | {rate:.0f} stocks/min | ETA: {eta:.0f}min",
                        flush=True,
                    )

                if processed % 200 == 0:
                    save_progress(current_idx, total_records)
                    print(f"  ** Checkpoint saved **", flush=True)

                if batch_idx < len(batches):
                    new_future = executor.submit(fetch_batch, batches[batch_idx])
                    futures[new_future] = batch_idx
                    batch_idx += 1

                break

    # Merge all chunks into final parquet
    print(f"\nMerging {chunk_id} chunks...", flush=True)
    chunks = sorted(chunk_dir.glob("*.parquet"))
    dfs = [pd.read_parquet(p) for p in chunks]
    if dfs:
        final = pd.concat(dfs, ignore_index=True)
        final["date"] = pd.to_datetime(final["date"])
        final = final.sort_values(["stock_code", "date", "datetime"]).reset_index(drop=True)
        final.to_parquet(OUTPUT_PATH, index=False)
        total_records = len(final)

    save_progress(start_idx + len(codes), total_records)
    total_time = time.time() - start_time
    print(f"Done! {total_records:,} records saved to {OUTPUT_PATH}", flush=True)
    print(f"Total time: {total_time/60:.1f} minutes ({total_time/3600:.1f} hours)", flush=True)


if __name__ == "__main__":
    main()
