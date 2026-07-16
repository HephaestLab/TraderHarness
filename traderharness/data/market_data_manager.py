"""MarketDataManager — 第一次回测自动拉取全市场数据并缓存到本地。

存储格式：
~/.traderharness/dataset/
├── daily.parquet      # 全市场日线，一个文件，按 stock_code 列区分
├── 5min.parquet       # 5分钟线，一个文件
└── metadata.json      # 拉取时间、股票数、数据范围

首次运行：mootdx 拉取 → 合并为单个 DataFrame → 存 parquet
后续运行：pd.read_parquet() 一次读完（秒级）
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from traderharness.paths import dataset_dir

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = dataset_dir()


class MarketDataManager:
    """管理本地市场数据缓存。单文件 parquet 存储。"""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def daily_path(self) -> Path:
        return self._cache_dir / "daily.parquet"

    @property
    def min5_path(self) -> Path:
        return self._cache_dir / "5min.parquet"

    @property
    def min5_chunks_dir(self) -> Path:
        return self._cache_dir / "5min_chunks"

    @property
    def min5_clean_dir(self) -> Path:
        """Cleaned, year-partitioned 5min dataset (see scripts/consolidate_5min.py)."""
        return self._cache_dir / "5min_clean"

    @property
    def metadata_path(self) -> Path:
        return self._cache_dir / "metadata.json"

    def has_daily_cache(self) -> bool:
        return self.daily_path.exists()

    def _dir_has_parquet(self, d: Path) -> bool:
        return d.exists() and any(d.rglob("*.parquet"))

    def has_5min_cache(self) -> bool:
        return (
            self.min5_path.exists()
            or self._dir_has_parquet(self.min5_clean_dir)
            or self._dir_has_parquet(self.min5_chunks_dir)
        )

    def load_daily(self, start_date: "date | None" = None, end_date: "date | None" = None) -> pd.DataFrame:
        """加载日线缓存。支持时间范围过滤（pyarrow pushdown）。"""
        if not self.has_daily_cache():
            self.fetch_daily()
        logger.info("Loading daily cache: %s", self.daily_path)

        if start_date or end_date:
            import pyarrow.dataset as ds
            import pyarrow as pa
            dataset = ds.dataset(self.daily_path, format="parquet")
            filters = []
            if start_date:
                filters.append(ds.field("date") >= pa.scalar(pd.Timestamp(start_date)))
            if end_date:
                filters.append(ds.field("date") <= pa.scalar(pd.Timestamp(end_date)))
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter = combined_filter & f
            table = dataset.to_table(filter=combined_filter)
            df = table.to_pandas()
        else:
            df = pd.read_parquet(self.daily_path)

        if "date" in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.date
            else:
                df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def load_5min(self, start_date: "date | None" = None, end_date: "date | None" = None) -> pd.DataFrame:
        """加载5分钟线缓存。

        优先级：5min_clean/（清洗+按年分区的5年全量）> 5min_chunks/（原始分片）
        > 5min.parquet（近期单文件）。pyarrow dataset 支持目录级 pushdown filter，
        并对 clean 目录按 year 分区做文件级剪枝，内存与速度都更优。
        """
        if not self.has_5min_cache():
            return pd.DataFrame()

        import pyarrow.dataset as ds

        # Prefer cleaned partitioned dataset > raw chunks > single recent file
        clean = self._dir_has_parquet(self.min5_clean_dir)
        if clean:
            dataset = ds.dataset(self.min5_clean_dir, format="parquet", partitioning="hive")
            logger.info("Loading 5min from clean dir: %s", self.min5_clean_dir)
        elif self._dir_has_parquet(self.min5_chunks_dir):
            dataset = ds.dataset(self.min5_chunks_dir, format="parquet")
            logger.info("Loading 5min from chunks dir: %s", self.min5_chunks_dir)
        else:
            dataset = ds.dataset(self.min5_path, format="parquet")
            logger.info("Loading 5min from single file: %s", self.min5_path)

        filters = []
        if start_date:
            filters.append(ds.field("date") >= pd.Timestamp(start_date))
        if end_date:
            filters.append(ds.field("date") <= pd.Timestamp(end_date))

        # Directory-level pruning on the year partition (clean dataset only).
        if clean and (start_date or end_date):
            y0 = (start_date or end_date).year
            y1 = (end_date or start_date).year
            filters.append(ds.field("year").isin(list(range(y0, y1 + 1))))

        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter = combined_filter & f
            table = dataset.to_table(filter=combined_filter)
        else:
            table = dataset.to_table()

        df = table.to_pandas()

        # Drop the year partition column so downstream schema is unchanged.
        if "year" in df.columns:
            df = df.drop(columns=["year"])

        # Normalize datetime column BEFORE converting date to python date.
        # Chunks have string time ("09:35:00"), single file has full timestamp.
        if "datetime" in df.columns and "date" in df.columns:
            sample = df["datetime"].iloc[0] if len(df) > 0 else ""
            if isinstance(sample, str) and len(sample) <= 8:
                df["datetime"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["datetime"])

        # Normalize date column to python date
        if "date" in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.date
            else:
                df["date"] = pd.to_datetime(df["date"]).dt.date

        return df

    def fetch_daily(self) -> None:
        """从 mootdx 拉取全市场日线并存为单个 parquet。8 并发。"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            from mootdx.quotes import Quotes
        except ImportError:
            raise ImportError("mootdx not installed. Run: pip install traderharness[data]")

        api = Quotes.factory(market="std")
        sh = api.stocks(market=1)
        sz = api.stocks(market=0)

        codes = []
        for _, row in sh.iterrows():
            c = str(row["code"]).zfill(6)
            if c.startswith(("600", "601", "603", "688")):
                codes.append(c)
        for _, row in sz.iterrows():
            c = str(row["code"]).zfill(6)
            if c.startswith(("000", "001", "002", "003", "300", "301")):
                codes.append(c)

        logger.info("Fetching daily bars for %d A-share stocks (8 workers)...", len(codes))
        t0 = time.time()

        local = threading.local()
        def get_api():
            if not hasattr(local, "api"):
                local.api = Quotes.factory(market="std")
            return local.api

        def fetch_one(code, max_retries=3):
            for attempt in range(max_retries):
                try:
                    api = get_api()
                    df = api.bars(symbol=code, frequency=9, offset=800)
                    if df is not None and len(df) > 30:
                        return pd.DataFrame({
                            "stock_code": code,
                            "date": pd.to_datetime(df.index).date,
                            "open": df["open"].values,
                            "high": df["high"].values,
                            "low": df["low"].values,
                            "close": df["close"].values,
                            "volume": (df["volume"] if "volume" in df.columns else df["vol"]).astype(int).values,
                        })
                    return None
                except Exception:
                    if attempt < max_retries - 1:
                        local.api = None  # force reconnect
                        time.sleep(0.5 * (attempt + 1))
                    else:
                        return None

        all_frames = []
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(fetch_one, c): c for c in codes}
            done = 0
            for f in as_completed(futures):
                done += 1
                result = f.result()
                if result is not None:
                    all_frames.append(result)
                if done % 1000 == 0:
                    logger.info("  daily: %d/%d (%.0fs)", done, len(codes), time.time() - t0)

        combined = pd.concat(all_frames, ignore_index=True)
        combined.to_parquet(self.daily_path, index=False)
        self._save_metadata("daily", len(all_frames), combined)
        logger.info("Daily cache saved: %d stocks, %d rows, %.0fs", len(all_frames), len(combined), time.time() - t0)

    def fetch_5min(self) -> None:
        """从 mootdx 拉取全市场 A 股5分钟线并存为单个 parquet。8 并发 + 翻页。"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            from mootdx.quotes import Quotes
        except ImportError:
            raise ImportError("mootdx not installed. Run: pip install traderharness[data]")

        api = Quotes.factory(market="std")
        sh = api.stocks(market=1)
        sz = api.stocks(market=0)

        codes = []
        for _, row in sh.iterrows():
            c = str(row["code"]).zfill(6)
            if c.startswith(("600", "601", "603", "688")):
                codes.append(c)
        for _, row in sz.iterrows():
            c = str(row["code"]).zfill(6)
            if c.startswith(("000", "001", "002", "003", "300", "301")):
                codes.append(c)

        logger.info("Fetching 5min bars for %d A-share stocks (8 workers, 15 pages each)...", len(codes))
        t0 = time.time()

        local = threading.local()
        def get_api():
            if not hasattr(local, "api"):
                local.api = Quotes.factory(market="std")
            return local.api

        def fetch_one_5min(code, max_retries=3):
            for attempt in range(max_retries):
                try:
                    api = get_api()
                    page_bars = []
                    for start in range(0, 12000, 800):
                        df = api.bars(symbol=code, frequency=0, offset=800, start=start)
                        if df is None or len(df) == 0:
                            break
                        page_bars.append(df)
                    if not page_bars:
                        return None
                    combined = pd.concat(page_bars).sort_index()
                    combined = combined[~combined.index.duplicated()]
                    return pd.DataFrame({
                        "stock_code": code,
                        "datetime": pd.to_datetime(combined.index),
                        "date": pd.to_datetime(combined.index).date,
                        "open": combined["open"].values,
                        "high": combined["high"].values,
                        "low": combined["low"].values,
                        "close": combined["close"].values,
                        "volume": (combined["volume"] if "volume" in combined.columns else combined["vol"]).astype(int).values,
                    })
                except Exception:
                    if attempt < max_retries - 1:
                        local.api = None
                        time.sleep(0.5 * (attempt + 1))
                    else:
                        return None

        all_frames = []
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(fetch_one_5min, c): c for c in codes}
            done = 0
            for f in as_completed(futures):
                done += 1
                result = f.result()
                if result is not None:
                    all_frames.append(result)
                if done % 500 == 0:
                    logger.info("  5min: %d/%d (%.0fs)", done, len(codes), time.time() - t0)

        if all_frames:
            combined = pd.concat(all_frames, ignore_index=True)
            combined.to_parquet(self.min5_path, index=False)
            self._save_metadata("5min", len(all_frames), combined)
        logger.info("5min cache saved: %d stocks, %.0fs", len(all_frames), time.time() - t0)

    def _save_metadata(self, data_type: str, stock_count: int, df: pd.DataFrame) -> None:
        meta = {}
        if self.metadata_path.exists():
            meta = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        meta[data_type] = {
            "stock_count": stock_count,
            "total_rows": len(df),
            "fetched_at": datetime.now().isoformat(),
            "date_range": [str(df["date"].min()), str(df["date"].max())] if "date" in df.columns else [],
        }
        self.metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

