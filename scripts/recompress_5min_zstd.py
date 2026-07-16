"""Recompress the 5min_clean/ parquet files in place with zstd.

Lossless: each file is read and rewritten with compression="zstd" (level 9).
The Hive year=YYYY/ partition structure is preserved (year lives in the path,
not the file), so the dataset loader keeps working unchanged.

Usage:
    cd D:\\finharness
    .venv\\Scripts\\python.exe scripts/recompress_5min_zstd.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pyarrow.parquet as pq

CLEAN_DIR = Path.home() / ".traderharness" / "dataset" / "5min_clean"


def main() -> None:
    files = sorted(CLEAN_DIR.rglob("*.parquet"))
    print(f"Recompressing {len(files)} files in {CLEAN_DIR} -> zstd ...", flush=True)
    t0 = time.time()
    before = after = 0
    for i, f in enumerate(files, 1):
        before += f.stat().st_size
        table = pq.read_table(f)
        tmp = f.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd", compression_level=9)
        tmp.replace(f)
        after += f.stat().st_size
        if i % 80 == 0 or i == len(files):
            print(
                f"  [{i}/{len(files)}] {before/1024/1024:,.0f}MB -> {after/1024/1024:,.0f}MB "
                f"| {time.time()-t0:.0f}s",
                flush=True,
            )
    print(
        f"Done: {before/1024/1024:,.0f}MB -> {after/1024/1024:,.0f}MB "
        f"({100*(1-after/before):.0f}% smaller) in {(time.time()-t0)/60:.1f} min",
        flush=True,
    )


if __name__ == "__main__":
    main()
