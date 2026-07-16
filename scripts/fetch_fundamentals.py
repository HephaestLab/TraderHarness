"""
Fetch fundamental data for all A-share stocks from BaoStock.
Stores as parquet at ~/.traderharness/dataset/fundamentals.parquet

Key: uses pubDate (actual publish date) for historical alignment.
Agent sees only data published before current_date.

Fields: stock_code, pub_date, stat_date, roe, net_profit_margin, gross_margin,
        net_profit, eps_ttm, revenue, yoy_revenue, yoy_net_profit, yoy_eps
"""

import sys
import time
import json
from pathlib import Path

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "fundamentals.parquet"
PROGRESS_PATH = DATASET_DIR / "fundamentals_progress.json"

START_YEAR = 2021
END_YEAR = 2026
DELAY = 0.5


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


def fetch_one_stock(bs_code: str) -> list:
    records = []
    for year in range(START_YEAR, END_YEAR + 1):
        for quarter in range(1, 5):
            # Profit data (ROE, margins, net profit, EPS, revenue)
            rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
            profit_row = None
            while rs.error_code == "0" and rs.next():
                profit_row = rs.get_row_data()

            # Growth data (YoY growth rates)
            rs2 = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
            growth_row = None
            while rs2.error_code == "0" and rs2.next():
                growth_row = rs2.get_row_data()

            if not profit_row:
                continue

            pub_date = profit_row[1]  # pubDate
            stat_date = profit_row[2]  # statDate

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


def _to_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def main():
    progress = load_progress()
    codes = get_stock_codes()
    start_idx = progress["last_index"]

    print(f"Fetching fundamentals: {len(codes)} stocks, {START_YEAR}-{END_YEAR}", flush=True)
    print(f"Resuming from index: {start_idx}", flush=True)

    lg = bs.login()
    if lg.error_code != "0":
        print(f"BaoStock login failed: {lg.error_msg}", flush=True)
        return

    all_records = []
    if OUTPUT_PATH.exists() and start_idx > 0:
        existing = pd.read_parquet(OUTPUT_PATH)
        all_records = existing.to_dict("records")
        print(f"Loaded {len(all_records)} existing records", flush=True)

    start_time = time.time()

    for i in range(start_idx, len(codes)):
        code = codes[i]
        bs_code = code_to_baostock(code)
        records = fetch_one_stock(bs_code)
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

        time.sleep(DELAY)

    bs.logout()

    df = pd.DataFrame(all_records)
    if len(df) > 0:
        df = df.drop_duplicates(subset=["stock_code", "stat_date"])
        df = df.sort_values(["stock_code", "pub_date"]).reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    save_progress(len(codes), len(df))

    total_time = time.time() - start_time
    print(f"\nDone! {len(df)} records saved to {OUTPUT_PATH}", flush=True)
    print(f"Stocks covered: {df['stock_code'].nunique()}", flush=True)
    print(f"Total time: {total_time/60:.1f} minutes", flush=True)


if __name__ == "__main__":
    main()
