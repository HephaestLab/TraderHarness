"""Atomically remove non-A-share rows from canonical announcements."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traderharness.data.entity_templates import (  # noqa: E402
    filter_a_share_announcements,
)
from traderharness.paths import dataset_dir  # noqa: E402


def main() -> None:
    path = dataset_dir() / "announcements.parquet"
    frame = pd.read_parquet(path)
    rows_before = len(frame)
    frame["stock_code"] = frame["stock_code"].astype(str).str.strip()
    cleaned = filter_a_share_announcements(frame)
    dedup_keys = ["stock_code", "title", "announcement_time"]
    cleaned = (
        cleaned.drop_duplicates(dedup_keys, keep="last")
        .sort_values(["announcement_time", "stock_code"])
        .reset_index(drop=True)
    )

    temporary = path.with_suffix(".parquet.tmp")
    cleaned.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)
    print(
        f"announcements: {rows_before:,} -> {len(cleaned):,} "
        f"(removed {rows_before - len(cleaned):,})"
    )


if __name__ == "__main__":
    main()
