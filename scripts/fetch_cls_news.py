"""
Fetch 5 years of financial news from CLS (财联社) using reverse-engineered sign.
Stores as parquet at ~/.traderharness/dataset/news_cls.parquet

Sign algorithm: MD5(SHA1(sorted_query_string))
Pagination: refresh_type=1 + last_time=previous_last_ctime (goes backward in time)
"""

import sys
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "news_cls.parquet"
PROGRESS_PATH = DATASET_DIR / "news_cls_progress.json"

URL = "https://www.cls.cn/v1/roll/get_roll_list"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cls.cn/telegraph",
}

TARGET_DATE = datetime(2021, 5, 15)
ITEMS_PER_PAGE = 50
DELAY = 0.3
CHECKPOINT_INTERVAL = 10000


def cls_sign(params: dict) -> str:
    sorted_keys = sorted(params.keys())
    query_str = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    sha1 = hashlib.sha1(query_str.encode()).hexdigest()
    return hashlib.md5(sha1.encode()).hexdigest()


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_time": None, "total_records": 0}


def save_progress(last_time, total_records):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_time": last_time, "total_records": total_records}, f)


def fetch_page(last_time: int, client: httpx.Client) -> list:
    params = {
        "app": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "rn": str(ITEMS_PER_PAGE),
        "last_time": str(last_time),
        "refresh_type": "1",
    }
    params["sign"] = cls_sign(params)

    for attempt in range(3):
        try:
            r = client.get(URL, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                result = r.json()
                return result.get("data", {}).get("roll_data", [])
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return []


def main():
    progress = load_progress()
    all_records = []

    if OUTPUT_PATH.exists() and progress["total_records"] > 0:
        existing = pd.read_parquet(OUTPUT_PATH)
        all_records = existing.to_dict("records")
        print(f"Loaded {len(all_records)} existing records", flush=True)

    # Start from current time or resume point
    if progress["last_time"]:
        last_time = progress["last_time"]
        print(f"Resuming from: {datetime.fromtimestamp(last_time)}", flush=True)
    else:
        last_time = int(time.time())
        print(f"Starting from now: {datetime.fromtimestamp(last_time)}", flush=True)

    target_ts = int(TARGET_DATE.timestamp())
    print(f"Target: {TARGET_DATE.date()} (ts={target_ts})", flush=True)

    start_time = time.time()
    page = 0
    consecutive_empty = 0

    with httpx.Client() as client:
        while last_time > target_ts:
            items = fetch_page(last_time, client)
            page += 1

            if not items:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    print("5 consecutive empty pages, stopping.", flush=True)
                    break
                time.sleep(2)
                continue

            consecutive_empty = 0

            for item in items:
                ctime = item.get("ctime", 0)
                if not ctime:
                    continue
                all_records.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "ctime": ctime,
                    "display_time": datetime.fromtimestamp(ctime),
                    "level": item.get("level", ""),
                    "tags": ",".join(t.get("name", "") for t in item.get("tags", []) if isinstance(t, dict)),
                    "stock_list": ",".join(s.get("name", "") for s in item.get("stock_list", []) if isinstance(s, dict)),
                })

            last_time = items[-1]["ctime"]
            earliest = datetime.fromtimestamp(last_time)

            if page % 50 == 0:
                elapsed = time.time() - start_time
                print(
                    f"  Page {page} | Records: {len(all_records):,} | Earliest: {earliest} | {page/(elapsed/60):.0f} pages/min",
                    flush=True,
                )

            if len(all_records) % CHECKPOINT_INTERVAL < ITEMS_PER_PAGE:
                df = pd.DataFrame(all_records)
                df.to_parquet(OUTPUT_PATH, index=False)
                save_progress(last_time, len(all_records))
                print(f"  ** Checkpoint: {len(all_records):,} records, earliest: {earliest} **", flush=True)

            time.sleep(DELAY)

    # Final save
    df = pd.DataFrame(all_records)
    if len(df) > 0:
        df["display_time"] = pd.to_datetime(df["display_time"])
        df = df.drop_duplicates(subset=["id"]).sort_values("display_time").reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    save_progress(last_time, len(df))

    total_time = time.time() - start_time
    print(f"\nDone! {len(df):,} news items saved to {OUTPUT_PATH}", flush=True)
    if len(df) > 0:
        print(f"Date range: {df['display_time'].min()} ~ {df['display_time'].max()}", flush=True)
    print(f"Total time: {total_time/60:.1f} minutes", flush=True)


if __name__ == "__main__":
    main()
