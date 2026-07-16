"""
Resume 5min backfill from where it actually stopped.
Checks existing chunks to determine real progress, adds reconnection logic.
Uses 16 workers with retry per batch.
"""

import sys
import time
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
CHUNK_DIR = DATASET_DIR / "5min_chunks"
OUTPUT_PATH = DATASET_DIR / "5min_full.parquet"
PROGRESS_PATH = DATASET_DIR / "5min_backfill_progress.json"
LOG_PATH = DATASET_DIR / "5min_resume.log"

START_DATE = "2021-05-15"
END_DATE = "2026-05-15"
WORKERS = 4
BATCH_SIZE = 5
FIELDS = "date,time,code,open,high,low,close,volume,amount"
MAX_RETRIES = 3


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_stock_codes() -> list[str]:
    daily_path = DATASET_DIR / "daily.parquet"
    df = pd.read_parquet(daily_path, columns=["stock_code"])
    return sorted(df["stock_code"].unique().tolist())


def get_already_fetched() -> set[str]:
    """Read all existing chunks to find which stocks are already done."""
    CHUNK_DIR.mkdir(exist_ok=True)
    chunks = list(CHUNK_DIR.glob("*.parquet"))
    if not chunks:
        return set()
    codes = set()
    for p in chunks:
        try:
            df = pd.read_parquet(p, columns=["stock_code"])
            codes.update(df["stock_code"].unique())
        except Exception:
            pass
    return codes


def code_to_baostock(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def fetch_batch(codes: list[str]) -> pd.DataFrame:
    """Fetch 5min data for a batch. Each process has its own BS connection with retry."""
    for attempt in range(MAX_RETRIES):
        lg = bs.login()
        if lg.error_code == "0":
            break
        time.sleep(2)
    else:
        return pd.DataFrame()

    all_dfs = []
    for code in codes:
        bs_code = code_to_baostock(code)
        try:
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
        except Exception:
            pass

    try:
        bs.logout()
    except Exception:
        pass

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined["datetime"] = (
        combined["time"].str[8:10] + ":" +
        combined["time"].str[10:12] + ":" +
        combined["time"].str[12:14]
    )
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined[combined["volume"] > 0]
    return combined[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]]


def main():
    codes = get_stock_codes()
    already_done = get_already_fetched()
    remaining = [c for c in codes if c not in already_done]

    log(f"Total stocks: {len(codes)}")
    log(f"Already fetched: {len(already_done)}")
    log(f"Remaining: {len(remaining)}")
    log(f"Workers: {WORKERS}, Batch size: {BATCH_SIZE}")

    if not remaining:
        log("All stocks done! Merging...")
        merge_chunks()
        return

    CHUNK_DIR.mkdir(exist_ok=True)
    chunk_id = len(list(CHUNK_DIR.glob("*.parquet")))

    batches = [remaining[i:i+BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    start_time = time.time()
    processed = 0
    total_records = 0

    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        futures = {}
        batch_idx = 0

        submit_count = min(WORKERS * 2, len(batches))
        for i in range(submit_count):
            future = executor.submit(fetch_batch, batches[i])
            futures[future] = i
            batch_idx = i + 1

        while futures:
            for future in as_completed(futures):
                bi = futures.pop(future)
                try:
                    df = future.result(timeout=600)
                    if not df.empty:
                        chunk_path = CHUNK_DIR / f"chunk_{chunk_id:05d}.parquet"
                        df.to_parquet(chunk_path, index=False)
                        total_records += len(df)
                        chunk_id += 1
                except Exception as e:
                    log(f"  Batch {bi} error: {e}")

                processed += BATCH_SIZE

                if processed % 50 == 0 or processed <= BATCH_SIZE:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed * 60 if elapsed > 0 else 0
                    eta = (len(remaining) - processed) / rate if rate > 0 else 0
                    log(f"  [{processed}/{len(remaining)}] Records: {total_records:,} | {rate:.0f} stocks/min | ETA: {eta:.0f}min")

                if batch_idx < len(batches):
                    new_future = executor.submit(fetch_batch, batches[batch_idx])
                    futures[new_future] = batch_idx
                    batch_idx += 1

                break

    log(f"\nFetch complete. Total new records: {total_records:,}")
    log("Merging all chunks...")
    merge_chunks()


def merge_chunks():
    chunks = sorted(CHUNK_DIR.glob("*.parquet"))
    log(f"Merging {len(chunks)} chunks...")

    dfs = []
    for p in chunks:
        try:
            dfs.append(pd.read_parquet(p))
        except Exception as e:
            log(f"  Skip corrupt chunk {p.name}: {e}")

    if not dfs:
        log("No data to merge!")
        return

    final = pd.concat(dfs, ignore_index=True)
    final["date"] = pd.to_datetime(final["date"])
    final = final.drop_duplicates(subset=["stock_code", "date", "datetime"])
    final = final.sort_values(["stock_code", "date", "datetime"]).reset_index(drop=True)
    final.to_parquet(OUTPUT_PATH, index=False)

    total_time = time.time()
    log(f"Done! {len(final):,} records | {final['stock_code'].nunique()} stocks")
    log(f"Date range: {final['date'].min()} ~ {final['date'].max()}")
    log(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
