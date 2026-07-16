"""
Single-threaded patch script to fill remaining gaps for valuation and 5min data.
Uses sequential BaoStock queries with reconnection between batches.
No multiprocessing — avoids the TCP disconnect issue from concurrent connections.
"""

import sys
import time
from pathlib import Path

import baostock as bs
import pandas as pd
import pyarrow.parquet as pq

DATASET_DIR = Path.home() / ".finharness" / "dataset"
CHUNK_DIR_5MIN = DATASET_DIR / "5min_chunks"
CHUNK_DIR_VAL = DATASET_DIR / "valuation_chunks"
LOG_PATH = DATASET_DIR / "patch_remaining.log"

START_DATE = "2021-05-15"
END_DATE = "2026-05-15"

FIELDS_5MIN = "date,time,code,open,high,low,close,volume,amount"
FIELDS_VAL = "date,code,turn,peTTM,pbMRQ,psTTM,isST"


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_all_codes() -> list[str]:
    df = pd.read_parquet(DATASET_DIR / "daily.parquet", columns=["stock_code"])
    return sorted(df["stock_code"].unique().tolist())


def get_done_codes(chunk_dir: Path) -> set[str]:
    chunk_dir.mkdir(exist_ok=True)
    codes = set()
    for p in chunk_dir.glob("*.parquet"):
        try:
            t = pq.read_table(str(p), columns=["stock_code"])
            codes.update(t.column(0).to_pylist())
        except Exception:
            pass
    return codes


def code_to_bs(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def connect() -> bool:
    for attempt in range(5):
        lg = bs.login()
        if lg.error_code == "0":
            return True
        time.sleep(3)
    return False


def fetch_5min_one(code: str) -> pd.DataFrame | None:
    bs_code = code_to_bs(code)
    rs = bs.query_history_k_data_plus(
        bs_code, FIELDS_5MIN,
        start_date=START_DATE, end_date=END_DATE,
        frequency="5", adjustflag="3"
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=FIELDS_5MIN.split(","))
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
    return df[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume", "amount"]]


def fetch_val_one(code: str) -> pd.DataFrame | None:
    bs_code = code_to_bs(code)
    rs = bs.query_history_k_data_plus(
        bs_code, FIELDS_VAL,
        start_date=START_DATE, end_date=END_DATE,
        frequency="d", adjustflag="3"
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=FIELDS_VAL.split(","))
    df["stock_code"] = code
    df["date"] = pd.to_datetime(df["date"])
    for col in ["turn", "peTTM", "pbMRQ", "psTTM"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["isST"] = df["isST"].astype(str).map({"1": True, "0": False}).fillna(False)
    df = df.rename(columns={"peTTM": "pe_ttm", "pbMRQ": "pb_mrq", "psTTM": "ps_ttm", "isST": "is_st"})
    df = df.drop(columns=["code"], errors="ignore")
    return df[["stock_code", "date", "turn", "pe_ttm", "pb_mrq", "ps_ttm", "is_st"]]


def run_task(task: str):
    all_codes = get_all_codes()

    if task == "valuation":
        chunk_dir = CHUNK_DIR_VAL
        fetch_fn = fetch_val_one
    elif task == "5min":
        chunk_dir = CHUNK_DIR_5MIN
        fetch_fn = fetch_5min_one
    else:
        print(f"Unknown task: {task}. Use 'valuation' or '5min'")
        return

    done = get_done_codes(chunk_dir)
    remaining = [c for c in all_codes if c not in done]
    log(f"[{task}] Total: {len(all_codes)}, Done: {len(done)}, Remaining: {len(remaining)}")

    if not remaining:
        log(f"[{task}] All done!")
        return

    chunk_id = len(list(chunk_dir.glob("*.parquet")))

    if not connect():
        log(f"[{task}] Failed to connect to BaoStock!")
        return

    start_time = time.time()
    fetched = 0
    empty = 0
    reconnect_every = 50

    for i, code in enumerate(remaining):
        if i > 0 and i % reconnect_every == 0:
            try:
                bs.logout()
            except Exception:
                pass
            time.sleep(1)
            if not connect():
                log(f"[{task}] Reconnect failed at {i}, stopping.")
                break

        try:
            df = fetch_fn(code)
            if df is not None and not df.empty:
                chunk_path = chunk_dir / f"chunk_{chunk_id:05d}.parquet"
                df.to_parquet(chunk_path, index=False)
                chunk_id += 1
                fetched += 1
            else:
                empty += 1
        except Exception as e:
            log(f"[{task}] Error {code}: {e}")
            empty += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed * 60
            log(f"[{task}] [{i+1}/{len(remaining)}] fetched={fetched} empty={empty} | {rate:.0f}/min")

    try:
        bs.logout()
    except Exception:
        pass

    elapsed = time.time() - start_time
    log(f"[{task}] Done! fetched={fetched}, empty={empty}, time={elapsed/60:.1f}min")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python patch_remaining.py <valuation|5min>")
        sys.exit(1)
    run_task(sys.argv[1])
