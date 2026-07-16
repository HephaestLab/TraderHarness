"""
Resume fundamentals fetch from where it actually stopped (index 1644).
Adds reconnection every 100 stocks to prevent silent BaoStock drops.
"""

import time
import json
from pathlib import Path

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
OUTPUT_PATH = DATASET_DIR / "fundamentals.parquet"
PROGRESS_PATH = DATASET_DIR / "fundamentals_progress.json"
LOG_PATH = DATASET_DIR / "fundamentals_resume.log"

START_YEAR = 2021
END_YEAR = 2026
RECONNECT_EVERY = 100
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


def code_to_baostock(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def _to_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def reconnect():
    try:
        bs.logout()
    except Exception:
        pass
    for attempt in range(MAX_RETRIES):
        lg = bs.login()
        if lg.error_code == "0":
            return True
        log(f"  Login attempt {attempt+1} failed: {lg.error_msg}")
        time.sleep(2)
    return False


def fetch_one_stock(bs_code: str) -> list[dict]:
    records = []
    for year in range(START_YEAR, END_YEAR + 1):
        for quarter in range(1, 5):
            rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
            profit_row = None
            while rs.error_code == "0" and rs.next():
                profit_row = rs.get_row_data()

            rs2 = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
            growth_row = None
            while rs2.error_code == "0" and rs2.next():
                growth_row = rs2.get_row_data()

            if not profit_row:
                continue

            pub_date = profit_row[1]
            stat_date = profit_row[2]
            if not pub_date or pub_date == "":
                continue

            record = {
                "stock_code": bs_code.split(".")[1],
                "pub_date": pub_date,
                "stat_date": stat_date,
                "roe": _to_float(profit_row[3]),
                "net_profit_margin": _to_float(profit_row[4]),
                "gross_margin": _to_float(profit_row[5]),
                "net_profit": _to_float(profit_row[6]),
                "eps_ttm": _to_float(profit_row[7]),
                "revenue": _to_float(profit_row[8]),
            }

            if growth_row and len(growth_row) >= 8:
                record["yoy_equity"] = _to_float(growth_row[3])
                record["yoy_asset"] = _to_float(growth_row[4])
                record["yoy_net_profit"] = _to_float(growth_row[5])
                record["yoy_eps"] = _to_float(growth_row[6])
                record["yoy_pni"] = _to_float(growth_row[7])

            records.append(record)

    return records


def main():
    codes = get_stock_codes()

    existing_df = pd.read_parquet(OUTPUT_PATH)
    covered = set(existing_df["stock_code"].unique())
    log(f"Existing: {len(covered)} stocks, {len(existing_df)} records")

    remaining = [(i, c) for i, c in enumerate(codes) if c not in covered]
    log(f"Remaining: {len(remaining)} stocks to fetch")

    if not remaining:
        log("Nothing to do!")
        return

    if not reconnect():
        log("FATAL: Cannot login to BaoStock")
        return

    new_records = []
    start_time = time.time()
    consecutive_empty = 0

    for batch_num, (i, code) in enumerate(remaining):
        if batch_num > 0 and batch_num % RECONNECT_EVERY == 0:
            log(f"  Reconnecting (every {RECONNECT_EVERY})...")
            if not reconnect():
                log("FATAL: Reconnect failed, saving progress")
                break
            consecutive_empty = 0

        bs_code = code_to_baostock(code)
        records = fetch_one_stock(bs_code)
        new_records.extend(records)

        if records:
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty >= 20:
                log(f"  WARNING: 20 consecutive empty, reconnecting...")
                if not reconnect():
                    log("FATAL: Reconnect failed")
                    break
                consecutive_empty = 0
                records = fetch_one_stock(bs_code)
                new_records.extend(records)
                if records:
                    consecutive_empty = 0

        if (batch_num + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (batch_num + 1) / elapsed * 60
            eta = (len(remaining) - batch_num - 1) / rate if rate > 0 else 0
            log(f"  [{batch_num+1}/{len(remaining)}] +{len(new_records)} new | {rate:.0f} stocks/min | ETA: {eta:.0f}min")

        if (batch_num + 1) % 200 == 0:
            _save_intermediate(existing_df, new_records)
            log(f"  ** Checkpoint saved **")

        time.sleep(0.3)

    try:
        bs.logout()
    except Exception:
        pass

    _save_intermediate(existing_df, new_records)
    total_time = time.time() - start_time
    final_df = pd.read_parquet(OUTPUT_PATH)
    log(f"\nDone! {len(final_df)} records | {final_df['stock_code'].nunique()} stocks")
    log(f"Total time: {total_time/60:.1f} minutes")


def _save_intermediate(existing_df: pd.DataFrame, new_records: list[dict]):
    if not new_records:
        return
    new_df = pd.DataFrame(new_records)
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["stock_code", "stat_date"])
    combined = combined.sort_values(["stock_code", "pub_date"]).reset_index(drop=True)
    combined.to_parquet(OUTPUT_PATH, index=False)


if __name__ == "__main__":
    main()
