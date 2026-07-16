"""Fetch CSI 300 (沪深300) index daily data from BaoStock.

Stores as parquet at ~/.finharness/dataset/index_300.parquet
"""

import time
from pathlib import Path

import baostock as bs
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "index_300.parquet"

START_DATE = "2021-05-15"
END_DATE = "2026-05-15"


def main():
    lg = bs.login()
    if lg.error_code != "0":
        print(f"Login failed: {lg.error_msg}")
        return

    print(f"Fetching CSI 300 index: {START_DATE} ~ {END_DATE}")

    rs = bs.query_history_k_data_plus(
        "sh.000300",
        "date,open,high,low,close,volume,amount",
        start_date=START_DATE,
        end_date=END_DATE,
        frequency="d",
    )

    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())

    bs.logout()

    if not rows:
        print("No data returned!")
        return

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)

    print(f"Done! {len(df)} records saved to {OUTPUT_PATH}")
    print(f"Date range: {df['date'].min()} ~ {df['date'].max()}")
    print(f"Close range: {df['close'].min():.2f} ~ {df['close'].max():.2f}")


if __name__ == "__main__":
    main()
