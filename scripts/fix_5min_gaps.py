"""Fix the two 5min_clean defects found by data_doctor:

1. Coverage/freshness gaps — stocks with daily bars but no matching 5min year,
   or active stocks whose last 5min bar lags their last positive-volume daily bar.
   Fix: derive missing ranges from canonical data and refetch them from BaoStock.

2. Cross-batch duplicates — consolidate_5min.py deduplicated per flush-batch
   only, so stocks split across batches (e.g. 000677) have every row twice.
   Fix: global dedup during the rebuild.

Pipeline:
    Step A  derive and fetch missing stock/date ranges -> gap_chunks/
    Step B  duckdb: read 5min_clean/ + gap_chunks/, normalize and deduplicate
            by year/code-prefix, then atomically replace each year.

Usage:
    .venv\\Scripts\\python.exe scripts/fix_5min_gaps.py [--skip-fetch]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traderharness.paths import dataset_dir  # noqa: E402

DATASET = dataset_dir()
CLEAN_DIR = DATASET / "5min_clean"
GAP_DIR = DATASET / "gap_chunks"
V2_DIR = DATASET / "5min_clean_v2"

FIELDS = "date,time,code,open,high,low,close,volume,amount"
WORKERS = 2
BATCH = 5
SOCKET_TIMEOUT = 45


def code_to_baostock(code: str) -> str:
    return f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"


def fetch_batch(job: tuple[int, list[tuple[str, str, str]]]) -> tuple[int, int, list[str]]:
    """One worker process: fetch a batch of (code, start, end); write one chunk file."""
    batch_id, items = job
    import socket

    import baostock as bs

    # BaoStock does not configure a socket timeout. A dead server connection
    # would otherwise block the entire five-year repair indefinitely.
    socket.setdefaulttimeout(SOCKET_TIMEOUT)
    try:
        lg = bs.login()
    except Exception:
        return batch_id, 0, [c for c, _, _ in items]
    if lg.error_code != "0":
        return batch_id, 0, [c for c, _, _ in items]

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    for code, start, end in items:
        try:
            rs = bs.query_history_k_data_plus(
                code_to_baostock(code), FIELDS,
                start_date=start, end_date=end, frequency="5", adjustflag="3",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=FIELDS.split(","))
                df["stock_code"] = code
                frames.append(df)
            else:
                failed.append(code)
        except Exception:
            failed.append(code)
    try:
        bs.logout()
    except Exception:
        pass

    n = 0
    if frames:
        out = pd.concat(frames, ignore_index=True)
        n = len(out)
        GAP_DIR.mkdir(parents=True, exist_ok=True)
        out.to_parquet(GAP_DIR / f"gap-{batch_id:04d}.parquet", index=False)
    return batch_id, n, failed


def step_a_fetch() -> None:
    import duckdb
    import pyarrow.dataset as pads

    daily = pd.read_parquet(DATASET / "daily.parquet", columns=["stock_code", "date"])
    daily["date"] = pd.to_datetime(daily["date"])
    daily["year"] = daily["date"].dt.year
    min5 = pads.dataset(CLEAN_DIR, format="parquet", partitioning="hive")
    today = pd.Timestamp.today().date()
    todo: list[tuple[str, str, str]] = []
    missing_by_year: dict[int, int] = {}
    for year in sorted(int(value) for value in daily["year"].unique()):
        daily_codes = set(
            daily.loc[daily["year"] == year, "stock_code"].astype(str).unique()
        )
        table = min5.to_table(
            columns=["stock_code"],
            filter=pads.field("year") == year,
        )
        min5_codes = set(table.column("stock_code").unique().to_pylist())
        missing = sorted(daily_codes - min5_codes)
        if not missing:
            continue
        missing_by_year[year] = len(missing)
        start = date(year, 1, 1)
        end = min(date(year, 12, 31), today)
        todo.extend((code, start.isoformat(), end.isoformat()) for code in missing)

    clean_glob = (CLEAN_DIR / "**" / "*.parquet").resolve().as_posix()
    con = duckdb.connect()
    try:
        latest_bars = con.execute(
            f"""
            SELECT stock_code, max(CAST(datetime AS DATE)) AS last_date
            FROM read_parquet('{clean_glob}', hive_partitioning=true)
            GROUP BY stock_code
            """
        ).fetchall()
    finally:
        con.close()
    last_bar_by_code = {str(code): pd.Timestamp(value).date() for code, value in latest_bars}
    daily_ranges = daily.groupby("stock_code")["date"].agg(["min", "max"])
    market_date = daily["date"].max()
    active_cutoff = market_date - pd.Timedelta(days=30)
    stale_ranges = 0
    for code, values in daily_ranges.iterrows():
        if values["max"] < active_cutoff:
            continue
        code = str(code)
        last_daily = values["max"].date()
        last_bar = last_bar_by_code.get(code)
        start = (
            last_bar + pd.Timedelta(days=1)
            if last_bar is not None
            else values["min"].date()
        )
        if start <= last_daily:
            todo.append((code, str(start), str(last_daily)))
            stale_ranges += 1

    detail = ", ".join(f"{year}:{count}" for year, count in missing_by_year.items())
    print(
        f"Step A: {len(todo)} repair ranges to fetch"
        + (f" (missing years {detail};" if detail else " (")
        + f" stale active stocks {stale_ranges})",
        flush=True,
    )
    if not todo:
        return

    existing_ids = [
        int(p.stem.split("-")[-1])
        for p in GAP_DIR.glob("gap-*.parquet")
        if p.stem.split("-")[-1].isdigit()
    ] if GAP_DIR.exists() else []
    first_id = max(existing_ids, default=-1) + 1
    jobs = [
        (first_id + i, todo[i * BATCH:(i + 1) * BATCH])
        for i in range((len(todo) + BATCH - 1) // BATCH)
    ]
    t0 = time.time()
    total = 0
    all_failed: list[str] = []
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_batch, j): j[0] for j in jobs}
        done = 0
        for fut in as_completed(futs):
            bid, n, failed = fut.result()
            total += n
            all_failed.extend(failed)
            done += 1
            print(
                f"  batch {bid} done ({done}/{len(jobs)}) "
                f"rows={n:,} failed={len(failed)} | total={total:,} | "
                f"{time.time()-t0:.0f}s",
                flush=True,
            )
    print(
        f"Step A complete: {total:,} rows fetched, "
        f"{len(all_failed)} stocks empty/failed",
        flush=True,
    )
    if all_failed:
        (GAP_DIR / "_failed_codes.json").write_text(
            json.dumps(sorted(all_failed)),
            encoding="utf-8",
        )


def step_b_rebuild() -> None:
    import shutil

    import duckdb

    print("Step B: year-local global dedup + rebuild via duckdb ...", flush=True)
    if V2_DIR.exists():
        shutil.rmtree(V2_DIR)
    con = duckdb.connect()
    con.execute(
        "SET memory_limit='4GB'; SET threads=2; SET preserve_insertion_order=false;"
    )
    temp_root = DATASET / "_duck_tmp"
    con.execute(f"SET temp_directory='{temp_root.as_posix()}';")
    con.execute("SET max_temp_directory_size='24GB';")

    gap_glob = str(GAP_DIR / "gap-*.parquet").replace("\\", "/")
    has_gaps = GAP_DIR.exists() and any(GAP_DIR.glob("gap-*.parquet"))
    t0 = time.time()
    years = sorted(
        int(path.name.split("=", 1)[1])
        for path in CLEAN_DIR.glob("year=*")
        if path.is_dir()
    )
    if has_gaps:
        gap_years = con.execute(
            f"""
            SELECT DISTINCT CAST(substr(time, 1, 4) AS INTEGER)
            FROM read_parquet('{gap_glob}')
            WHERE time IS NOT NULL
            """
        ).fetchall()
        years = sorted(set(years) | {int(row[0]) for row in gap_years})

    total_rows = 0
    try:
        for year in years:
            target = CLEAN_DIR / f"year={year}"
            temporary = DATASET / f".5min-year={year}-rebuild"
            backup = DATASET / f".5min-year={year}-backup"
            for path in (temporary, backup):
                if path.exists():
                    shutil.rmtree(path)
            temporary.mkdir(parents=True)

            sources: list[str] = []
            if target.exists() and any(target.glob("*.parquet")):
                existing_glob = (target / "*.parquet").as_posix()
                sources.append(
                    f"""
                    SELECT stock_code, CAST(date AS DATE) AS date, datetime,
                           CAST(open AS DOUBLE) AS open, CAST(high AS DOUBLE) AS high,
                           CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close,
                           CAST(volume AS DOUBLE) AS volume,
                           CAST(amount AS DOUBLE) AS amount, 0 AS _priority
                    FROM read_parquet('{existing_glob}')
                    """
                )
            if has_gaps:
                sources.append(
                    f"""
                    SELECT stock_code,
                           CAST(strptime(substr(time,1,8), '%Y%m%d') AS DATE) AS date,
                           strptime(substr(time,1,14), '%Y%m%d%H%M%S') AS datetime,
                           CAST(open AS DOUBLE) AS open, CAST(high AS DOUBLE) AS high,
                           CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close,
                           CAST(volume AS DOUBLE) AS volume,
                           CAST(amount AS DOUBLE) AS amount, 1 AS _priority
                    FROM read_parquet('{gap_glob}')
                    WHERE substr(time, 1, 4) = '{year}'
                      AND CAST(volume AS DOUBLE) > 0
                    """
                )
            union = " UNION ALL ".join(f"({source})" for source in sources)
            prefixes = [
                str(row[0])
                for row in con.execute(
                    f"""
                    SELECT DISTINCT substr(stock_code, 1, 1)
                    FROM ({union})
                    WHERE stock_code IS NOT NULL
                    ORDER BY 1
                    """
                ).fetchall()
            ]

            year_rows = 0
            try:
                for prefix in prefixes:
                    output = (temporary / f"part-{prefix}.parquet").as_posix()
                    copied = con.execute(
                        f"""
                        COPY (
                            SELECT stock_code, date, datetime, open, high, low,
                                   close, volume, amount
                            FROM ({union})
                            WHERE stock_code LIKE '{prefix}%'
                              AND (
                                  datetime::TIME BETWEEN TIME '09:30' AND TIME '11:30'
                                  OR datetime::TIME BETWEEN TIME '13:00' AND TIME '15:00'
                              )
                            QUALIFY row_number() OVER (
                                PARTITION BY stock_code, datetime
                                ORDER BY _priority DESC, volume DESC
                            ) = 1
                        ) TO '{output}' (FORMAT parquet, COMPRESSION zstd)
                        """
                    ).fetchone()
                    year_rows += int(copied[0])

                if target.exists():
                    target.rename(backup)
                temporary.rename(target)
                if backup.exists():
                    shutil.rmtree(backup)
            except Exception:
                if temporary.exists():
                    shutil.rmtree(temporary)
                if not target.exists() and backup.exists():
                    backup.rename(target)
                raise

            total_rows += year_rows
            print(
                f"  year {year}: {year_rows:,} rows | "
                f"{(time.time() - t0) / 60:.1f} min",
                flush=True,
            )
    finally:
        con.close()
        if temp_root.exists():
            shutil.rmtree(temp_root)

    print(
        f"Step B complete: {total_rows:,} rows | {(time.time()-t0)/60:.1f} min",
        flush=True,
    )


def refresh_metadata() -> None:
    import pyarrow.dataset as pads
    daily = pd.read_parquet(DATASET / "daily.parquet", columns=["stock_code", "date"])
    dset = pads.dataset(CLEAN_DIR, format="parquet", partitioning="hive")
    n5 = dset.count_rows()
    unique_codes = (
        dset.to_table(columns=["stock_code"]).column("stock_code").unique().to_pylist()
    )
    codes5 = len(set(unique_codes))
    meta_p = DATASET / "metadata.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    meta["daily"] = {
        "stock_count": int(daily["stock_code"].nunique()),
        "total_rows": int(len(daily)),
        "date_range": [str(daily["date"].min().date()), str(daily["date"].max().date())],
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    meta["5min"] = {
        "stock_count": codes5,
        "total_rows": int(n5),
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": (
            "baostock 5y + legacy mootdx + gap backfill; global dedup "
            "(fix_5min_gaps.py); year-partitioned zstd at 5min_clean/"
        ),
    }
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("metadata.json refreshed", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-rebuild", action="store_true")
    args = ap.parse_args()
    if not args.skip_fetch:
        step_a_fetch()
    if not args.skip_rebuild:
        step_b_rebuild()
        refresh_metadata()
    print("DONE", flush=True)
