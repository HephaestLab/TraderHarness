"""
Parallel 5min backfill for remaining stocks.
Uses cache file to skip slow chunk scan. 4 workers with reconnect per batch.
Each worker fetches full 5-year data for one stock at a time.

Usage:
    cd D:\\finharness
    .venv\\Scripts\\python.exe scripts/patch_5min_parallel.py
"""

import time
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
CHUNK_DIR = DATASET_DIR / "5min_chunks"
CACHE_PATH = DATASET_DIR / "5min_done_codes.json"
LOG_PATH = DATASET_DIR / "patch_5min_parallel.log"

START_DATE = "2021-05-15"
END_DATE = "2026-05-15"
FIELDS = "date,time,code,open,high,low,close,volume,amount"
WORKERS = 2
BATCH_SIZE = 1
MAX_RETRIES = 3


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_remaining() -> list[str]:
    all_codes = sorted(
        pd.read_parquet(DATASET_DIR / "daily.parquet", columns=["stock_code"])
        ["stock_code"].unique().tolist()
    )
    with open(CACHE_PATH) as f:
        done = set(json.load(f))
    return [c for c in all_codes if c not in done]


def fetch_batch(codes: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Fetch 5min data for a batch. Returns (df, list_of_codes_attempted)."""
    for attempt in range(MAX_RETRIES):
        lg = bs.login()
        if lg.error_code == "0":
            break
        time.sleep(2)
    else:
        return pd.DataFrame(), codes

    all_dfs = []
    for code in codes:
        bs_code = f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"
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
        return pd.DataFrame(), codes

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
    return combined[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]], codes


def main():
    remaining = get_remaining()
    log(f"Remaining: {len(remaining)} stocks | Workers: {WORKERS}, Batch: {BATCH_SIZE}")

    if not remaining:
        log("All done!")
        return

    CHUNK_DIR.mkdir(exist_ok=True)
    chunk_id = len(list(CHUNK_DIR.glob("*.parquet")))
    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]

    start_time = time.time()
    processed = 0
    fetched = 0
    total_records = 0
    all_done_codes = []

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
                    result = future.result(timeout=600)
                    df, codes_attempted = result
                    all_done_codes.extend(codes_attempted)
                    if not df.empty:
                        chunk_path = CHUNK_DIR / f"chunk_{chunk_id:05d}.parquet"
                        df.to_parquet(chunk_path, index=False)
                        total_records += len(df)
                        fetched += df["stock_code"].nunique()
                        chunk_id += 1
                except Exception as e:
                    log(f"  Batch {bi} error: {e}")

                processed += BATCH_SIZE

                if processed % 20 == 0 or processed <= BATCH_SIZE:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed * 60 if elapsed > 0 else 0
                    eta = (len(remaining) - processed) / rate if rate > 0 else 0
                    log(f"  [{processed}/{len(remaining)}] fetched={fetched} records={total_records:,} | {rate:.0f}/min | ETA: {eta:.0f}min")
                    # Save cache
                    with open(CACHE_PATH) as f:
                        cache = set(json.load(f))
                    cache.update(all_done_codes)
                    with open(CACHE_PATH, "w") as f:
                        json.dump(sorted(cache), f)
                    all_done_codes = []

                if batch_idx < len(batches):
                    new_future = executor.submit(fetch_batch, batches[batch_idx])
                    futures[new_future] = batch_idx
                    batch_idx += 1

                break

    # Final cache save
    if all_done_codes:
        with open(CACHE_PATH) as f:
            cache = set(json.load(f))
        cache.update(all_done_codes)
        with open(CACHE_PATH, "w") as f:
            json.dump(sorted(cache), f)

    elapsed = time.time() - start_time
    log(f"Done! fetched={fetched}, records={total_records:,}, time={elapsed/60:.1f}min")


if __name__ == "__main__":
    main()
