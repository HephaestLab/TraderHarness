"""
Fetch 5 years of financial news from Wallstreet CN (华尔街见闻).
Stores as parquet at ~/.traderharness/dataset/news_wallstreetcn.parquet

Fields: id, title, content, display_time, tags, symbols, channel
Timestamp precision: seconds (Unix timestamp)

Uses cursor-based pagination. Saves checkpoints every 5000 records.
Expected volume: ~500 items/day × 1800 days ≈ 900K items.
"""

import httpx
import time
import json
import sys
from datetime import datetime, date
from pathlib import Path
import pandas as pd

DATASET_DIR = Path.home() / ".traderharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "news_wallstreetcn.parquet"
PROGRESS_PATH = DATASET_DIR / "news_wallstreetcn_progress.json"

URL = "https://api-one-wscn.awtmt.com/apiv1/content/lives"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

TARGET_DATE = datetime(2021, 5, 15)
ITEMS_PER_PAGE = 100
DELAY_BETWEEN_REQUESTS = 0.3
CHECKPOINT_INTERVAL = 5000


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"cursor": None, "total_records": 0, "earliest_time": None}


def save_progress(cursor, total_records, earliest_time):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({
            "cursor": cursor,
            "total_records": total_records,
            "earliest_time": earliest_time,
        }, f)


def fetch_page(cursor, client: httpx.Client) -> tuple:
    params = {"channel": "global-channel", "limit": str(ITEMS_PER_PAGE)}
    if cursor:
        params["cursor"] = str(cursor)

    for attempt in range(3):
        try:
            r = client.get(URL, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                result = r.json()
                items = result.get("data", {}).get("items", [])
                next_cursor = result.get("data", {}).get("next_cursor", "")
                return items, next_cursor
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                print(f"  FAILED after 3 attempts: {e}", flush=True)
                return [], None
    return [], None


def parse_item(item: dict) -> dict:
    tags = item.get("tags", [])
    tag_names = [t.get("name", "") for t in tags] if isinstance(tags, list) else []
    symbols = item.get("symbols", [])
    symbol_names = [s.get("name", "") for s in symbols] if isinstance(symbols, list) else []

    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "content": item.get("content_text", ""),
        "display_time": datetime.fromtimestamp(item["display_time"]),
        "tags": ",".join(tag_names),
        "symbols": ",".join(symbol_names),
        "channel": item.get("global_channel_name", ""),
    }


def main():
    progress = load_progress()
    all_records = []

    if OUTPUT_PATH.exists() and progress["total_records"] > 0:
        existing_df = pd.read_parquet(OUTPUT_PATH)
        all_records = existing_df.to_dict("records")
        print(f"Loaded {len(all_records)} existing records", flush=True)

    cursor = progress["cursor"]
    target_ts = TARGET_DATE.timestamp()

    print(f"Fetching news from Wallstreet CN", flush=True)
    print(f"Target: back to {TARGET_DATE.date()} (5 years)", flush=True)
    print(f"Resuming from cursor: {cursor or 'latest'}", flush=True)
    if progress["earliest_time"]:
        print(f"Earliest so far: {progress['earliest_time']}", flush=True)

    page = 0
    consecutive_empty = 0

    with httpx.Client() as client:
        while True:
            items, next_cursor = fetch_page(cursor, client)
            page += 1

            if not items:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print("3 consecutive empty pages, stopping.", flush=True)
                    break
                time.sleep(2)
                continue

            consecutive_empty = 0

            for item in items:
                if "display_time" not in item or not item["display_time"]:
                    continue
                record = parse_item(item)
                all_records.append(record)

            earliest_in_batch = datetime.fromtimestamp(items[-1]["display_time"])

            if page % 50 == 0:
                print(
                    f"  Page {page} | Records: {len(all_records)} | Earliest: {earliest_in_batch}",
                    flush=True,
                )

            if len(all_records) % CHECKPOINT_INTERVAL < ITEMS_PER_PAGE and len(all_records) >= CHECKPOINT_INTERVAL:
                df = pd.DataFrame(all_records)
                df.to_parquet(OUTPUT_PATH, index=False)
                save_progress(cursor, len(all_records), str(earliest_in_batch))
                print(f"  ** Checkpoint: {len(all_records)} records, earliest: {earliest_in_batch} **", flush=True)

            if earliest_in_batch.timestamp() <= target_ts:
                print(f"Reached target date! Earliest: {earliest_in_batch}", flush=True)
                break

            if not next_cursor:
                print("No next cursor, reached the end.", flush=True)
                break

            cursor = next_cursor
            time.sleep(DELAY_BETWEEN_REQUESTS)

    df = pd.DataFrame(all_records)
    if len(df) > 0:
        df["display_time"] = pd.to_datetime(df["display_time"])
        df = df.drop_duplicates(subset=["id"]).sort_values("display_time").reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    save_progress(cursor, len(df), str(df["display_time"].min()) if len(df) > 0 else None)

    print(f"\nDone! {len(df)} news items saved to {OUTPUT_PATH}", flush=True)
    if len(df) > 0:
        print(f"Date range: {df['display_time'].min()} ~ {df['display_time'].max()}", flush=True)


if __name__ == "__main__":
    main()
