"""
Fetch business segment (主营业务构成) data for all A-share stocks.
Source: AKShare (东方财富)
Stores as parquet at ~/.finharness/dataset/business_segments.parquet

Contains: revenue breakdown by product/region for each reporting period.
Date masking: uses conservative pub_date estimation from report_date.
"""

import time
import json
from pathlib import Path
from datetime import date, timedelta

import akshare as ak
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "business_segments.parquet"
PROGRESS_PATH = DATASET_DIR / "business_segments_progress.json"
LOG_PATH = DATASET_DIR / "business_segments.log"

# Only keep data from 2020 onwards (sufficient for 5-year backtest starting 2021)
MIN_REPORT_DATE = date(2020, 1, 1)


def log(msg: str):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_index": 0, "total_records": 0}


def save_progress(last_index: int, total_records: int):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_index": last_index, "total_records": total_records}, f)


def get_stock_codes() -> list[str]:
    daily_path = DATASET_DIR / "daily.parquet"
    df = pd.read_parquet(daily_path, columns=["stock_code"])
    return sorted(df["stock_code"].unique().tolist())


def estimate_pub_date(report_date: date) -> date:
    """Conservative estimate of when a report becomes public.

    Rules (based on A-share disclosure regulations):
    - Annual report (12-31): published by April 30 next year → +120 days
    - Semi-annual report (06-30): published by August 31 → +62 days
    - Q1 report (03-31): published by April 30 → +30 days
    - Q3 report (09-30): published by October 31 → +31 days
    """
    month = report_date.month
    if month == 12:
        return date(report_date.year + 1, 4, 30)
    elif month == 6:
        return date(report_date.year, 8, 31)
    elif month == 3:
        return date(report_date.year, 4, 30)
    elif month == 9:
        return date(report_date.year, 10, 31)
    else:
        return report_date + timedelta(days=90)


def code_to_symbol(code: str) -> str:
    """Convert 6-digit code to AKShare symbol format (SH/SZ prefix)."""
    if code.startswith(("6", "9")):
        return f"SH{code}"
    return f"SZ{code}"


def fetch_one_stock(code: str) -> list[dict]:
    """Fetch business segment data for one stock."""
    symbol = code_to_symbol(code)
    try:
        df = ak.stock_zygc_em(symbol=symbol)
    except Exception:
        return []

    if df is None or df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        report_date = row.get("报告日期")
        if report_date is None:
            continue
        if isinstance(report_date, str):
            report_date = date.fromisoformat(report_date)
        if report_date < MIN_REPORT_DATE:
            continue

        pub_date = estimate_pub_date(report_date)

        record = {
            "stock_code": code,
            "report_date": str(report_date),
            "pub_date": str(pub_date),
            "segment_type": row.get("分类类型", ""),
            "segment_name": row.get("分类方向", ""),
            "revenue": row.get("营业收入"),
            "revenue_pct": row.get("营收占比"),
            "cost": row.get("营业成本"),
            "cost_pct": row.get("成本占比"),
            "profit": row.get("营业利润"),
            "profit_pct": row.get("利润占比"),
            "gross_margin": row.get("毛利率"),
        }
        records.append(record)

    return records


def main():
    progress = load_progress()
    codes = get_stock_codes()
    start_idx = progress["last_index"]

    log(f"Fetching business segments: {len(codes)} stocks")
    log(f"Resuming from index: {start_idx}")

    all_records = []
    if OUTPUT_PATH.exists() and start_idx > 0:
        existing = pd.read_parquet(OUTPUT_PATH)
        all_records = existing.to_dict("records")
        log(f"Loaded {len(all_records)} existing records")

    start_time = time.time()
    consecutive_errors = 0

    for i in range(start_idx, len(codes)):
        code = codes[i]
        try:
            records = fetch_one_stock(code)
            all_records.extend(records)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                log(f"  10 consecutive errors, pausing 60s...")
                time.sleep(60)
                consecutive_errors = 0

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            done = i - start_idx + 1
            rate = done / elapsed * 60 if elapsed > 0 else 0
            eta = (len(codes) - i - 1) / rate if rate > 0 else 0
            log(f"  [{i+1}/{len(codes)}] +{len(records)} | Total: {len(all_records)} | {rate:.0f} stocks/min | ETA: {eta:.0f}min")

        if (i + 1) % 200 == 0:
            df = pd.DataFrame(all_records)
            df.to_parquet(OUTPUT_PATH, index=False)
            save_progress(i + 1, len(all_records))
            log(f"  ** Checkpoint: {len(all_records)} records **")

        # Rate limiting: ~1 req/s is safe for East Money
        time.sleep(0.8)

    # Final save
    df = pd.DataFrame(all_records)
    if len(df) > 0:
        df = df.drop_duplicates(subset=["stock_code", "report_date", "segment_type", "segment_name"])
        df = df.sort_values(["stock_code", "report_date", "segment_type"]).reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    save_progress(len(codes), len(df))

    total_time = time.time() - start_time
    log(f"\nDone! {len(df)} records saved to {OUTPUT_PATH}")
    log(f"Stocks covered: {df['stock_code'].nunique() if len(df) > 0 else 0}")
    log(f"Total time: {total_time/60:.1f} minutes")


if __name__ == "__main__":
    main()
