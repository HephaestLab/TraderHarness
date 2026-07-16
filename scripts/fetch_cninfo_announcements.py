"""
Fetch 5 years of A-share announcements from cninfo (巨潮资讯).
Stores as parquet at ~/.finharness/dataset/announcements.parquet

Strategy: 1-day chunks, 3 days fetched in parallel, 10 concurrent pages per day.
This balances: small chunk size (fewer pages) + multi-day parallelism.
"""

import asyncio
import httpx
import time
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd

DATASET_DIR = Path.home() / ".finharness" / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "announcements.parquet"
PROGRESS_PATH = DATASET_DIR / "announcements_progress.json"

URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    "Origin": "http://www.cninfo.com.cn",
    "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
}

START_DATE = date(2021, 5, 15)
END_DATE = date(2026, 5, 14)
PAGE_SIZE = 30  # server hard limit
CONCURRENT_PAGES = 20  # parallel page requests within one day
CONCURRENT_DAYS = 5  # days fetched simultaneously


def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"last_date": None, "total_records": 0}


def save_progress(last_date, total_records):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"last_date": last_date, "total_records": total_records}, f)


def generate_dates(start: date, end: date) -> list:
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


async def fetch_page(client: httpx.AsyncClient, se_date: str, page_num: int, sem: asyncio.Semaphore) -> list:
    async with sem:
        data = {
            "pageNum": str(page_num),
            "pageSize": str(PAGE_SIZE),
            "tabName": "fulltext",
            "seDate": se_date,
            "isHLtitle": "true",
        }
        for attempt in range(3):
            try:
                r = await client.post(URL, data=data, headers=HEADERS, timeout=30)
                if r.status_code == 200:
                    return r.json().get("announcements") or []
                if r.status_code in (502, 504, 599):
                    await asyncio.sleep(1 + attempt)
                    continue
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
        return []


async def fetch_one_day(client: httpx.AsyncClient, target_date: date, sem: asyncio.Semaphore) -> list:
    se_date = f"{target_date}~{target_date}"

    # No column = all exchanges in one query (szse + sse + bse)
    data = {
        "pageNum": "1",
        "pageSize": str(PAGE_SIZE),
        "tabName": "fulltext",
        "seDate": se_date,
        "isHLtitle": "true",
    }
    for attempt in range(3):
        try:
            async with sem:
                r = await client.post(URL, data=data, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                result = r.json()
                break
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1)
            else:
                return []
    else:
        return []

    first_page = result.get("announcements") or []
    total = result.get("totalAnnouncement", 0)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    all_anns = list(first_page)

    if total_pages > 1:
        tasks = [fetch_page(client, se_date, p, sem) for p in range(2, total_pages + 1)]
        pages = await asyncio.gather(*tasks)
        for page_anns in pages:
            all_anns.extend(page_anns)

    records = []
    for ann in all_anns:
        ts = ann.get("announcementTime", 0)
        if not ts:
            continue
        records.append({
            "stock_code": ann.get("secCode", ""),
            "stock_name": ann.get("secName", ""),
            "title": ann.get("announcementTitle", ""),
            "announcement_time": datetime.fromtimestamp(ts / 1000),
            "pdf_url": ann.get("adjunctUrl", ""),
            "ann_type": ann.get("announcementTypeName", ""),
        })

    return records


async def main():
    progress = load_progress()
    existing_count = progress["total_records"]

    dates = generate_dates(START_DATE, END_DATE)
    if progress["last_date"]:
        last = date.fromisoformat(progress["last_date"])
        dates = [d for d in dates if d > last]

    print(f"Fetching announcements: {len(dates)} days remaining ({START_DATE} ~ {END_DATE})", flush=True)
    print(f"Concurrency: {CONCURRENT_PAGES} pages x {CONCURRENT_DAYS} days parallel", flush=True)
    print(f"Resuming from: {progress['last_date'] or 'start'} ({existing_count} existing)", flush=True)

    sem = asyncio.Semaphore(CONCURRENT_PAGES)
    start_time = time.time()
    batch_records = []
    total_new = 0

    async with httpx.AsyncClient() as client:
        for batch_start in range(0, len(dates), CONCURRENT_DAYS):
            batch = dates[batch_start:batch_start + CONCURRENT_DAYS]
            tasks = [fetch_one_day(client, d, sem) for d in batch]
            results = await asyncio.gather(*tasks)

            batch_total = 0
            for records in results:
                batch_records.extend(records)
                batch_total += len(records)
            total_new += batch_total

            i = batch_start + len(batch)
            elapsed = time.time() - start_time
            rate = i / elapsed * 60 if elapsed > 0 else 0
            eta_min = (len(dates) - i) / rate if rate > 0 else 0

            print(
                f"  [{i}/{len(dates)}] {batch[0]}~{batch[-1]} | +{batch_total} | New: {total_new} | {rate:.0f} days/min | ETA: {eta_min:.0f}min",
                flush=True,
            )

            # Checkpoint: append to parquet every 30 days
            if i % 30 < CONCURRENT_DAYS and batch_records:
                _save_batch(batch_records)
                save_progress(str(batch[-1]), existing_count + total_new)
                print(f"  ** Checkpoint: +{len(batch_records)} appended, total ~{existing_count + total_new} **", flush=True)
                batch_records = []

    # Final flush
    if batch_records:
        _save_batch(batch_records)

    save_progress(str(END_DATE), existing_count + total_new)
    total_time = time.time() - start_time
    print(f"\nDone! +{total_new} new records (total ~{existing_count + total_new})", flush=True)
    print(f"Saved to: {OUTPUT_PATH}", flush=True)
    print(f"Total time: {total_time/60:.1f} minutes", flush=True)

    # Final sort & dedup
    print("Final sort & dedup...", flush=True)
    df = pd.read_parquet(OUTPUT_PATH)
    df["announcement_time"] = pd.to_datetime(df["announcement_time"])
    df = df.drop_duplicates(subset=["stock_code", "title", "announcement_time"])
    df = df.sort_values("announcement_time").reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Final: {len(df)} unique records, {df['announcement_time'].min()} ~ {df['announcement_time'].max()}", flush=True)


def _save_batch(records: list):
    """Append records to parquet file."""
    new_df = pd.DataFrame(records)
    if OUTPUT_PATH.exists():
        existing = pd.read_parquet(OUTPUT_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_parquet(OUTPUT_PATH, index=False)


if __name__ == "__main__":
    asyncio.run(main())
