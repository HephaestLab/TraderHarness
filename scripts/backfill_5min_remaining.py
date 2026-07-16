"""Backfill remaining 5min stocks. Single-process, reliable."""
import json
import time
import sys
from pathlib import Path

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
CHUNK_DIR = DATASET_DIR / "5min_chunks"
START_DATE = "2021-05-15"
END_DATE = "2026-05-15"
FIELDS = "date,time,code,open,high,low,close,volume,amount"


def code_to_baostock(code: str) -> str:
    return f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"


def main():
    remaining = json.loads((DATASET_DIR / "5min_remaining_codes.json").read_text())
    print(f"Backfilling {len(remaining)} stocks...", flush=True)

    lg = bs.login()
    if lg.error_code != "0":
        print(f"Login failed: {lg.error_msg}")
        return

    chunk_idx = len(list(CHUNK_DIR.glob("chunk_*.parquet")))
    batch_dfs = []
    done = 0
    no_data = 0

    for i, code in enumerate(remaining):
        bs_code = code_to_baostock(code)
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, FIELDS,
                start_date=START_DATE, end_date=END_DATE,
                frequency="5",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=FIELDS.split(","))
                df["stock_code"] = code
                batch_dfs.append(df)
                done += 1
            else:
                no_data += 1
        except Exception as e:
            print(f"  Error {code}: {e}", flush=True)

        if (i + 1) % 10 == 0 and batch_dfs:
            _save_batch(batch_dfs, chunk_idx)
            chunk_idx += 1
            batch_dfs = []
            print(f"  [{i+1}/{len(remaining)}] done={done} no_data={no_data}", flush=True)

        if (i + 1) % 100 == 0:
            bs.logout()
            time.sleep(2)
            lg = bs.login()
            if lg.error_code != "0":
                print(f"Reconnect failed at {i+1}", flush=True)
                break

    if batch_dfs:
        _save_batch(batch_dfs, chunk_idx)

    bs.logout()
    print(f"\nDone. {done} with data, {no_data} empty, out of {len(remaining)}.")


def _save_batch(batch_dfs, chunk_idx):
    combined = pd.concat(batch_dfs, ignore_index=True)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined["date"] = pd.to_datetime(combined["date"])
    combined.rename(columns={"time": "datetime"}, inplace=True)
    if "code" in combined.columns:
        combined.drop(columns=["code"], inplace=True)
    chunk_path = CHUNK_DIR / f"chunk_{chunk_idx:05d}.parquet"
    combined.to_parquet(chunk_path, index=False)


if __name__ == "__main__":
    main()
