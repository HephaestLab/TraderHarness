"""拉取近 5 年全市场 A 股日线 + 5 分钟线数据（BaoStock）。

输出：
  ~/.traderharness/dataset/daily.parquet   （全市场日线，stock_code 列区分）
  ~/.traderharness/dataset/5min.parquet    （全市场5分钟线）
  ~/.traderharness/dataset/metadata.json   （元信息）

使用 multiprocessing 并行（BaoStock 不支持多线程）。
"""

import json
import logging
import time
from datetime import date, datetime
from multiprocessing import Pool, cpu_count
from pathlib import Path

import baostock as bs
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path.home() / ".traderharness" / "dataset"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2020-01-01"
END_DATE = date.today().isoformat()

WORKERS = 8  # BaoStock 建议不超过 10 个进程


def get_all_a_share_codes() -> list[str]:
    """获取全市场 A 股代码列表。"""
    lg = bs.login()
    rs = bs.query_stock_industry(code="", date="2024-06-03")
    codes = []
    seen = set()
    while rs.next():
        row = rs.get_row_data()
        code = row[1]  # e.g., "sh.600519"
        if code in seen:
            continue
        seen.add(code)
        num = code.split(".")[1]
        # 只要 A 股主板/创业板/科创板
        if num.startswith(("6", "0", "3")):
            codes.append(code)
    bs.logout()
    logger.info("Found %d A-share stocks", len(codes))
    return codes


def fetch_daily_one(code: str) -> pd.DataFrame | None:
    """拉取单只股票的日线数据。每个进程独立 login。"""
    try:
        lg = bs.login()
        rs = bs.query_history_k_data_plus(
            code,
            "date,code,open,high,low,close,volume,amount",
            start_date=START_DATE,
            end_date=END_DATE,
            frequency="d",
            adjustflag="3",  # 不复权（原始价格）
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "code", "open", "high", "low", "close", "volume", "amount"])
        df["stock_code"] = code.split(".")[1]
        df["date"] = pd.to_datetime(df["date"]).dt.date
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df[["stock_code", "date", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        try:
            bs.logout()
        except:
            pass
        return None


def fetch_5min_one(code: str) -> pd.DataFrame | None:
    """拉取单只股票的5分钟线数据。"""
    try:
        lg = bs.login()
        rs = bs.query_history_k_data_plus(
            code,
            "date,time,code,open,high,low,close,volume,amount",
            start_date=START_DATE,
            end_date=END_DATE,
            frequency="5",
            adjustflag="3",
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "time", "code", "open", "high", "low", "close", "volume", "amount"])
        df["stock_code"] = code.split(".")[1]
        df["date"] = pd.to_datetime(df["date"]).dt.date
        # time format: "20240304093500000" → "09:35:00"
        df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].str[8:10] + ":" + df["time"].str[10:12])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df[["stock_code", "date", "datetime", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        try:
            bs.logout()
        except:
            pass
        return None


def main():
    codes = get_all_a_share_codes()

    # === 日线 ===
    logger.info("=== Fetching daily data (%d stocks, %s ~ %s) ===", len(codes), START_DATE, END_DATE)
    t0 = time.time()
    with Pool(processes=WORKERS) as pool:
        results = []
        for i, result in enumerate(pool.imap_unordered(fetch_daily_one, codes), 1):
            if result is not None:
                results.append(result)
            if i % 500 == 0:
                logger.info("  daily: %d/%d done (%.0fs)", i, len(codes), time.time() - t0)

    daily_df = pd.concat(results, ignore_index=True)
    daily_path = OUTPUT_DIR / "daily.parquet"
    daily_df.to_parquet(daily_path, index=False)
    daily_time = time.time() - t0
    logger.info("Daily saved: %d stocks, %d rows, %.1f MB, %.0fs",
                daily_df["stock_code"].nunique(), len(daily_df),
                daily_path.stat().st_size / 1024 / 1024, daily_time)

    # === 5分钟线 ===
    logger.info("=== Fetching 5min data (%d stocks, %s ~ %s) ===", len(codes), START_DATE, END_DATE)
    t1 = time.time()
    with Pool(processes=WORKERS) as pool:
        results_5m = []
        for i, result in enumerate(pool.imap_unordered(fetch_5min_one, codes), 1):
            if result is not None:
                results_5m.append(result)
            if i % 200 == 0:
                logger.info("  5min: %d/%d done (%.0fs)", i, len(codes), time.time() - t1)

    min5_df = pd.concat(results_5m, ignore_index=True)
    min5_path = OUTPUT_DIR / "5min.parquet"
    min5_df.to_parquet(min5_path, index=False)
    min5_time = time.time() - t1
    logger.info("5min saved: %d stocks, %d rows, %.1f MB, %.0fs",
                min5_df["stock_code"].nunique(), len(min5_df),
                min5_path.stat().st_size / 1024 / 1024, min5_time)

    # === Metadata ===
    meta = {
        "source": "baostock",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": {
            "stocks": int(daily_df["stock_code"].nunique()),
            "rows": len(daily_df),
            "size_mb": round(daily_path.stat().st_size / 1024 / 1024, 1),
            "fetch_time_s": round(daily_time),
        },
        "5min": {
            "stocks": int(min5_df["stock_code"].nunique()),
            "rows": len(min5_df),
            "size_mb": round(min5_path.stat().st_size / 1024 / 1024, 1),
            "fetch_time_s": round(min5_time),
        },
        "created_at": datetime.now().isoformat(),
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("=== COMPLETE ===")
    logger.info("Daily: %.1f MB in %.0fs", daily_path.stat().st_size / 1024 / 1024, daily_time)
    logger.info("5min:  %.1f MB in %.0fs", min5_path.stat().st_size / 1024 / 1024, min5_time)
    logger.info("Total: %.1f MB in %.0fs", (daily_path.stat().st_size + min5_path.stat().st_size) / 1024 / 1024, daily_time + min5_time)
    logger.info("Output: %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()
