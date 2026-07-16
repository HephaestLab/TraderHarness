"""
Backfill daily kline data from 2021-05-15 to 2022-09-01 using BaoStock.
Merges with existing daily.parquet to create full 5-year dataset.
"""

import sys
import time
import json
from datetime import date
from pathlib import Path

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
OUTPUT_PATH = DATASET_DIR / "daily.parquet"
BACKFILL_PATH = DATASET_DIR / "daily_backfill.parquet"
PROGRESS_PATH = DATASET_DIR / "daily_backfill_progress.json"

START_DATE = "2021-05-15"
END_DATE = "2022-09-01"
FIELDS = "date,code,open,high,low,close,volume,amount"


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_index": 0, "total_records": 0}


def save_progress(last_index, total_records):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_index": last_index, "total_records": total_records}, f)


def get_stock_codes():
    """Get all stock codes from existing daily data."""
    df = pd.read_parquet(OUTPUT_PATH, columns=["stock_code"])
    codes = sorted(df["stock_code"].unique().tolist())
    return codes


def code_to_baostock(code: str) -> str:
    """Convert 6-digit code to baostock format (sh./sz.)."""
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def fetch_one_stock(bs_code: str) -> pd.DataFrame:
    rs = bs.query_history_k_data_plus(
        bs_code, FIELDS,
        start_date=START_DATE, end_date=END_DATE,
        frequency="d", adjustflag="3"
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=FIELDS.split(","))
    df["date"] = pd.to_datetime(df["date"])
    df["stock_code"] = bs_code.split(".")[1]
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["volume"] > 0]
    return df[["stock_code", "date", "open", "high", "low", "close", "volume", "amount"]]


def main():
    progress = load_progress()
    codes = get_stock_codes()
    print(f"Backfilling daily data: {len(codes)} stocks, {START_DATE} ~ {END_DATE}", flush=True)
    print(f"Resuming from index: {progress['last_index']}", flush=True)

    lg = bs.login()
    if lg.error_code != "0":
        print(f"BaoStock login failed: {lg.error_msg}", flush=True)
        return

    all_dfs = []
    if BACKFILL_PATH.exists() and progress["last_index"] > 0:
        existing = pd.read_parquet(BACKFILL_PATH)
        all_dfs.append(existing)
        print(f"Loaded {len(existing)} existing backfill records", flush=True)

    start_time = time.time()
    start_idx = progress["last_index"]
    new_records = 0

    for i in range(start_idx, len(codes)):
        code = codes[i]
        bs_code = code_to_baostock(code)
        df = fetch_one_stock(bs_code)
        if not df.empty:
            all_dfs.append(df)
            new_records += len(df)

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            done = i - start_idx + 1
            rate = done / elapsed * 60 if elapsed > 0 else 0
            eta = (len(codes) - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1}/{len(codes)}] +{new_records} records | {rate:.0f} stocks/min | ETA: {eta:.0f}min",
                flush=True,
            )

        if (i + 1) % 500 == 0:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined.to_parquet(BACKFILL_PATH, index=False)
            save_progress(i + 1, len(combined))
            print(f"  ** Checkpoint: {len(combined)} records **", flush=True)

    bs.logout()

    # Save backfill
    if all_dfs:
        backfill = pd.concat(all_dfs, ignore_index=True)
        backfill.to_parquet(BACKFILL_PATH, index=False)
        print(f"\nBackfill complete: {len(backfill)} records", flush=True)

        # Merge with existing daily.parquet
        print("Merging with existing daily.parquet...", flush=True)
        existing_daily = pd.read_parquet(OUTPUT_PATH)
        merged = pd.concat([backfill, existing_daily], ignore_index=True)
        merged["date"] = pd.to_datetime(merged["date"])
        merged = merged.drop_duplicates(subset=["stock_code", "date"])
        merged = merged.sort_values(["stock_code", "date"]).reset_index(drop=True)
        merged.to_parquet(OUTPUT_PATH, index=False)
        print(f"Merged daily.parquet: {len(merged)} records", flush=True)
        print(f"Date range: {merged['date'].min()} ~ {merged['date'].max()}", flush=True)

    save_progress(len(codes), len(backfill) if all_dfs else 0)
    total_time = time.time() - start_time
    print(f"Total time: {total_time/60:.1f} minutes", flush=True)


if __name__ == "__main__":
    main()
