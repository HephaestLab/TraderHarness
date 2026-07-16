"""
5min backfill for remaining ~984 stocks via BaoStock.
Uses 1-month query granularity to stay under throttle limits.
Saves progress after every stock. Re-runnable (skips done codes).

Expected time: ~1.5-2 min/stock → 984 stocks → ~25-33 hours total.
Can be interrupted and resumed at any time.

Usage:
    cd D:\\finharness
    .venv\\Scripts\\python.exe scripts/patch_5min_fast.py
"""

import time
import json
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
CHUNK_DIR = DATASET_DIR / "5min_chunks"
CACHE_PATH = DATASET_DIR / "5min_done_codes.json"
LOG_PATH = DATASET_DIR / "patch_5min.log"

FIELDS = "date,time,code,open,high,low,close,volume,amount"
RECONNECT_EVERY = 5

START = date(2021, 5, 15)
END = date(2026, 5, 15)


def make_monthly_ranges() -> list[tuple[str, str]]:
    ranges = []
    cur = START
    while cur < END:
        nxt = cur + relativedelta(months=1)
        if nxt > END:
            nxt = END
        ranges.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return ranges


MONTHS = make_monthly_ranges()


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


def connect() -> bool:
    for _ in range(5):
        lg = bs.login()
        if lg.error_code == "0":
            return True
        time.sleep(5)
    return False


def fetch_one(code: str) -> pd.DataFrame | None:
    bs_code = f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"
    all_rows = []
    for start_d, end_d in MONTHS:
        rs = bs.query_history_k_data_plus(
            bs_code, FIELDS,
            start_date=start_d, end_date=end_d,
            frequency="5", adjustflag="3"
        )
        while rs.error_code == "0" and rs.next():
            all_rows.append(rs.get_row_data())

    if not all_rows:
        return None
    df = pd.DataFrame(all_rows, columns=FIELDS.split(","))
    df["stock_code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df["datetime"] = (
        df["time"].str[8:10] + ":" +
        df["time"].str[10:12] + ":" +
        df["time"].str[12:14]
    )
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["volume"] > 0]
    df = df.drop_duplicates(subset=["stock_code", "date", "datetime"])
    return df[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]]


def save_cache(done_codes: list[str]):
    with open(CACHE_PATH) as f:
        cache = set(json.load(f))
    cache.update(done_codes)
    with open(CACHE_PATH, "w") as f:
        json.dump(sorted(cache), f)


def main():
    remaining = get_remaining()
    log(f"Remaining: {len(remaining)} stocks (monthly mode, {len(MONTHS)} months each)")

    if not remaining:
        log("All done!")
        return

    chunk_id = len(list(CHUNK_DIR.glob("*.parquet")))
    if not connect():
        log("Failed to connect!")
        return

    start_time = time.time()
    fetched = 0
    empty = 0

    for i, code in enumerate(remaining):
        if i > 0 and i % RECONNECT_EVERY == 0:
            try:
                bs.logout()
            except Exception:
                pass
            time.sleep(3)
            if not connect():
                log(f"Reconnect failed at {i}, stopping.")
                break

        stock_start = time.time()
        try:
            df = fetch_one(code)
            if df is not None and not df.empty:
                chunk_path = CHUNK_DIR / f"chunk_{chunk_id:05d}.parquet"
                df.to_parquet(chunk_path, index=False)
                chunk_id += 1
                fetched += 1
            else:
                empty += 1
        except Exception as e:
            log(f"  Error {code}: {e}")
            empty += 1

        stock_elapsed = time.time() - stock_start
        save_cache([code])

        if (i + 1) % 5 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed * 60
            eta = (len(remaining) - i - 1) / rate if rate > 0 else 0
            log(f"  [{i+1}/{len(remaining)}] fetched={fetched} empty={empty} | {rate:.1f}/min | ETA: {eta:.0f}min | last: {stock_elapsed:.0f}s")

    try:
        bs.logout()
    except Exception:
        pass

    elapsed = time.time() - start_time
    log(f"Done! fetched={fetched}, empty={empty}, time={elapsed/60:.1f}min")


if __name__ == "__main__":
    main()
