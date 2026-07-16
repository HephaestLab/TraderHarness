"""
Fetch dividend/bonus/split data for all A-share stocks.
Stores as parquet at ~/.traderharness/dataset/dividends.parquet

Fields: stock_code, ann_date, bonus_shares, transfer_shares, cash_dividend,
        ex_date, record_date, progress
"""

import sys
import time
import json
from datetime import date
from pathlib import Path

import akshare as ak
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "dividends.parquet"
PROGRESS_PATH = DATASET_DIR / "dividends_progress.json"

START_YEAR = 2021


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_index": 0, "total_records": 0}


def save_progress(last_index, total_records):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_index": last_index, "total_records": total_records}, f)


def get_all_stock_codes():
    """Get stock codes from existing daily data."""
    daily_path = DATASET_DIR / "daily.parquet"
    if daily_path.exists():
        df = pd.read_parquet(daily_path, columns=["stock_code"])
        codes = sorted(df["stock_code"].unique().tolist())
        return codes
    return []


def fetch_one_stock(code: str) -> list:
    records = []
    try:
        df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df is None or df.empty:
            return []

        for _, row in df.iterrows():
            ann_date = row.get("公告日期")
            if ann_date is pd.NaT or ann_date is None:
                continue

            # Filter to recent 5 years only
            if hasattr(ann_date, "year") and ann_date.year < START_YEAR:
                continue

            ex_date = row.get("除权除息日")
            record_date = row.get("股权登记日")
            progress = row.get("进度", "")

            records.append({
                "stock_code": code,
                "ann_date": str(ann_date)[:10] if ann_date is not pd.NaT else None,
                "bonus_shares": float(row.get("送股", 0) or 0),
                "transfer_shares": float(row.get("转增", 0) or 0),
                "cash_dividend": float(row.get("派息", 0) or 0),
                "ex_date": str(ex_date)[:10] if ex_date is not pd.NaT and ex_date is not None else None,
                "record_date": str(record_date)[:10] if record_date is not pd.NaT and record_date is not None else None,
                "progress": progress,
            })
    except Exception:
        pass
    return records


def main():
    progress = load_progress()
    codes = get_all_stock_codes()
    if not codes:
        print("No stock codes found in daily.parquet", flush=True)
        return

    print(f"Fetching dividend data for {len(codes)} stocks", flush=True)
    print(f"Resuming from index: {progress['last_index']}", flush=True)

    all_records = []
    if OUTPUT_PATH.exists() and progress["last_index"] > 0:
        existing = pd.read_parquet(OUTPUT_PATH)
        all_records = existing.to_dict("records")
        print(f"Loaded {len(all_records)} existing records", flush=True)

    start_time = time.time()
    start_idx = progress["last_index"]

    for i in range(start_idx, len(codes)):
        code = codes[i]
        records = fetch_one_stock(code)
        all_records.extend(records)

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            done = i - start_idx + 1
            rate = done / elapsed * 60 if elapsed > 0 else 0
            eta = (len(codes) - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1}/{len(codes)}] +{len(records)} | Total: {len(all_records)} | {rate:.0f} stocks/min | ETA: {eta:.0f}min",
                flush=True,
            )

        if (i + 1) % 200 == 0:
            df = pd.DataFrame(all_records)
            df.to_parquet(OUTPUT_PATH, index=False)
            save_progress(i + 1, len(all_records))
            print(f"  ** Checkpoint: {len(all_records)} records **", flush=True)

        time.sleep(0.3)

    df = pd.DataFrame(all_records)
    if len(df) > 0:
        df = df.drop_duplicates()
        df = df.sort_values(["stock_code", "ann_date"]).reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    save_progress(len(codes), len(df))

    total_time = time.time() - start_time
    print(f"\nDone! {len(df)} dividend records saved to {OUTPUT_PATH}", flush=True)
    print(f"Stocks with dividends: {df['stock_code'].nunique()}", flush=True)
    print(f"Total time: {total_time/60:.1f} minutes", flush=True)


if __name__ == "__main__":
    main()
