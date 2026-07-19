"""Data doctor — full-dataset health check & reconciliation report.

Run after any data fetch/patch operation. Exits non-zero when a hard check
fails, so it can gate releases and CI-style validation.

Checks
------
1. Presence: every expected dataset file/dir exists and is readable.
2. Time ranges: daily / valuation / index_300 / announcements / fundamentals
   aligned to the same 5-year window; end dates within tolerance of each other.
3. Daily vs 5min coverage per year: every (stock, year) that has daily bars
   must have 5min bars in 5min_clean/ (hard threshold, default 99%).
4. 5min integrity on sampled stocks: bars/day within [30, 48], no duplicate
   (stock, datetime) pairs.
5. metadata.json freshness: recorded ranges/counts match reality.

Usage:
    .venv\\Scripts\\python.exe scripts/data_doctor.py [--coverage-threshold 0.99] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.dataset as pads

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traderharness.data.stock_registry_loader import (  # noqa: E402
    is_a_share_stock_code,
)
from traderharness.paths import dataset_dir  # noqa: E402

DATASET = dataset_dir()

EXPECTED_FILES = [
    "daily.parquet",
    "dividends.parquet",
    "fundamentals.parquet",
    "valuation.parquet",
    "announcements.parquet",
    "news_cls.parquet",
    "index_300.parquet",
]

report: dict = {"checks": [], "generated_at": datetime.now().isoformat(timespec="seconds")}
_failed_hard = False


def check(name: str, ok: bool, detail: str, hard: bool = True) -> None:
    global _failed_hard
    status = "PASS" if ok else ("FAIL" if hard else "WARN")
    if not ok and hard:
        _failed_hard = True
    report["checks"].append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage-threshold", type=float, default=0.99)
    ap.add_argument("--sample-stocks", type=int, default=20)
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()

    # --- 1. presence ---
    for f in EXPECTED_FILES:
        p = DATASET / f
        detail = f"{p} ({p.stat().st_size / 1e6:.0f} MB)" if p.exists() else f"{p} missing"
        check(f"presence:{f}", p.exists(), detail)
    clean_dir = DATASET / "5min_clean"
    has_clean = clean_dir.exists() and any(clean_dir.rglob("*.parquet"))
    check("presence:5min_clean/", has_clean, str(clean_dir))
    if _failed_hard:
        _write(args)
        return 1

    # --- 2. time ranges ---
    daily = pd.read_parquet(
        DATASET / "daily.parquet",
        columns=["stock_code", "date", "volume"],
    )
    d_min, d_max = daily["date"].min(), daily["date"].max()
    check(
        "range:daily",
        True,
        f"{d_min.date()} -> {d_max.date()}, "
        f"{daily['stock_code'].nunique()} stocks, {len(daily):,} rows",
    )

    ends = {"daily": d_max}
    for name, col in [("valuation", "date"), ("index_300", "date"), ("fundamentals", "pub_date")]:
        df = pd.read_parquet(DATASET / f"{name}.parquet", columns=[col])
        ends[name] = pd.to_datetime(df[col]).max()
    ann = pd.read_parquet(
        DATASET / "announcements.parquet",
        columns=["stock_code", "announcement_time"],
    )
    ends["announcements"] = pd.to_datetime(ann["announcement_time"]).max()
    invalid_announcements = int((~ann["stock_code"].astype(str).map(is_a_share_stock_code)).sum())
    check(
        "universe:announcements-a-share",
        invalid_announcements == 0,
        f"{invalid_announcements:,}/{len(ann):,} rows have non-A-share codes",
    )
    news = pd.read_parquet(DATASET / "news_cls.parquet", columns=["ctime"])
    ends["news_cls"] = pd.to_datetime(news["ctime"], unit="s")
    ends["news_cls"] = ends["news_cls"].max()

    market_ends = {name: value for name, value in ends.items() if name != "fundamentals"}
    spread = (max(market_ends.values()) - min(market_ends.values())).days
    detail = ", ".join(f"{key}={value.date()}" for key, value in market_ends.items())
    check(
        "range:market-end-alignment",
        spread <= 7,
        f"spread={spread}d | {detail}",
    )
    fundamentals_lag = (d_max - ends["fundamentals"]).days
    check(
        "range:fundamentals-freshness",
        fundamentals_lag <= 120,
        f"lag={fundamentals_lag}d | pub_date={ends['fundamentals'].date()}",
    )

    # --- 3. daily vs 5min coverage per year ---
    dset = pads.dataset(clean_dir, format="parquet", partitioning="hive")
    daily["year"] = daily["date"].dt.year
    worst: list[str] = []
    min_ratio = 1.0
    coverage: dict[int, dict] = {}
    for year in sorted(daily["year"].unique()):
        d_codes = set(daily.loc[daily["year"] == year, "stock_code"].unique())
        t = dset.to_table(columns=["stock_code"], filter=(pads.field("year") == int(year)))
        m_codes = set(t.column("stock_code").unique().to_pylist())
        missing = d_codes - m_codes
        ratio = 1 - len(missing) / max(len(d_codes), 1)
        coverage[int(year)] = {
            "daily_stocks": len(d_codes),
            "missing_5min": len(missing),
            "ratio": round(ratio, 4),
        }
        min_ratio = min(min_ratio, ratio)
        if missing:
            worst.extend(sorted(missing)[:3])
    report["coverage_by_year"] = coverage
    by_year_txt = ", ".join(f"{y}: {c['ratio']:.2%}" for y, c in coverage.items())
    check(
        "coverage:daily-vs-5min",
        min_ratio >= args.coverage_threshold,
        f"min year ratio={min_ratio:.2%} (threshold {args.coverage_threshold:.0%}) [{by_year_txt}]"
        + (f" sample_missing={worst[:6]}" if worst else ""),
    )

    # --- 4. Per-stock freshness for recently active stocks ---
    traded_daily = daily.loc[pd.to_numeric(daily["volume"], errors="coerce") > 0]
    last_daily = traded_daily.groupby("stock_code")["date"].max()
    active_cutoff = last_daily.max() - pd.Timedelta(days=30)
    active_last_daily = last_daily.loc[last_daily >= active_cutoff]
    clean_glob = (clean_dir / "**" / "*.parquet").resolve().as_posix()
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"""
            SELECT stock_code, max(CAST(datetime AS DATE)) AS last_date
            FROM read_parquet('{clean_glob}', hive_partitioning=true)
            GROUP BY stock_code
            """
        ).fetchall()
    finally:
        con.close()
    last_min5 = {str(code): pd.Timestamp(value) for code, value in rows}
    stale = {
        str(code): {
            "daily": str(value.date()),
            "min5": (str(last_min5[str(code)].date()) if str(code) in last_min5 else None),
        }
        for code, value in active_last_daily.items()
        if str(code) not in last_min5 or last_min5[str(code)] < value.normalize()
    }
    report["stale_active_stocks"] = stale
    check(
        "freshness:active-stock-5min",
        not stale,
        f"{len(stale)}/{len(active_last_daily)} active stocks lag their last daily bar"
        + (f" sample={list(stale.items())[:3]}" if stale else ""),
    )

    # --- 5. 5min integrity on sampled stocks ---
    all_codes = sorted(daily["stock_code"].unique())
    random.seed(42)
    sample = random.sample(all_codes, min(args.sample_stocks, len(all_codes)))
    bad_days = 0
    dups = 0
    checked_days = 0
    for code in sample:
        t = dset.to_table(filter=(pads.field("stock_code") == code)).to_pandas()
        if t.empty:
            continue
        dups += int(t.duplicated(subset=["datetime"]).sum())
        per_day = t.groupby(t["datetime"].dt.date).size()
        checked_days += len(per_day)
        bad_days += int(((per_day < 30) | (per_day > 48)).sum())
    check(
        "integrity:5min-duplicates",
        dups == 0,
        f"{dups} duplicate (stock,datetime) in {len(sample)} sampled stocks",
    )
    check(
        "integrity:5min-bars-per-day",
        bad_days / max(checked_days, 1) < 0.01,
        f"{bad_days}/{checked_days} sampled days outside [30,48] bars",
        hard=False,
    )

    # --- 6. metadata freshness ---
    meta_p = DATASET / "metadata.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        rec = meta.get("daily", {}).get("date_range", [None, None])
        actual = [str(d_min.date()), str(d_max.date())]
        check("metadata:daily-range", rec == actual, f"recorded={rec} actual={actual}", hard=False)
    else:
        check("metadata:exists", False, "metadata.json missing", hard=False)

    _write(args)
    outcome = "ALL HARD CHECKS PASSED" if not _failed_hard else "HARD CHECK FAILURES — see above"
    print("\n=> " + outcome)
    return 1 if _failed_hard else 0


def _write(args) -> None:
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    sys.exit(main())
