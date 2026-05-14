"""MarketDataManager — 第一次回测自动拉取全市场数据并缓存到本地。

存储格式：
~/.finharness/market_cache/
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

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".finharness" / "market_cache"


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
    def metadata_path(self) -> Path:
        return self._cache_dir / "metadata.json"

    def has_daily_cache(self) -> bool:
        return self.daily_path.exists()

    def has_5min_cache(self) -> bool:
        return self.min5_path.exists()

    def load_daily(self) -> pd.DataFrame:
        """加载日线缓存。返回 DataFrame(stock_code, date, open, high, low, close, volume)。"""
        if not self.has_daily_cache():
            self.fetch_daily()
        logger.info("Loading daily cache: %s", self.daily_path)
        df = pd.read_parquet(self.daily_path)
        if "date" in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.date
            else:
                df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def load_5min(self) -> pd.DataFrame:
        """加载5分钟线缓存。"""
        if not self.has_5min_cache():
            self.fetch_5min()
        logger.info("Loading 5min cache: %s", self.min5_path)
        df = pd.read_parquet(self.min5_path)
        if "date" in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.date
            else:
                df["date"] = pd.to_datetime(df["date"]).dt.date
        return df

    def fetch_daily(self) -> None:
        """从 mootdx 拉取全市场日线并存为单个 parquet。"""
        try:
            from mootdx.quotes import Quotes
        except ImportError:
            raise ImportError("mootdx not installed. Run: pip install finharness[data]")

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

        logger.info("Fetching daily bars for %d A-share stocks...", len(codes))
        t0 = time.time()
        all_frames = []

        for i, code in enumerate(codes):
            try:
                df = api.bars(symbol=code, frequency=9, offset=800)
                if df is not None and len(df) > 30:
                    out = pd.DataFrame({
                        "stock_code": code,
                        "date": pd.to_datetime(df.index).date,
                        "open": df["open"].values,
                        "high": df["high"].values,
                        "low": df["low"].values,
                        "close": df["close"].values,
                        "volume": (df["volume"] if "volume" in df.columns else df["vol"]).astype(int).values,
                    })
                    all_frames.append(out)
            except Exception:
                pass
            if (i + 1) % 500 == 0:
                logger.info("  %d/%d fetched (%.0fs)", i + 1, len(codes), time.time() - t0)

        combined = pd.concat(all_frames, ignore_index=True)
        combined.to_parquet(self.daily_path, index=False)
        self._save_metadata("daily", len(all_frames), combined)
        logger.info("Daily cache saved: %d stocks, %d rows, %.0fs", len(all_frames), len(combined), time.time() - t0)

    def fetch_5min(self) -> None:
        """从 mootdx 拉取全市场 A 股5分钟线并存为单个 parquet。"""
        try:
            from mootdx.quotes import Quotes
        except ImportError:
            raise ImportError("mootdx not installed. Run: pip install finharness[data]")

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

        logger.info("Fetching 5min bars for %d A-share stocks (pagination)...", len(codes))
        t0 = time.time()
        all_frames = []

        for i, code in enumerate(codes):
            page_bars = []
            for start in range(0, 12000, 800):
                df = api.bars(symbol=code, frequency=0, offset=800, start=start)
                if df is None or len(df) == 0:
                    break
                page_bars.append(df)
            if page_bars:
                combined = pd.concat(page_bars).sort_index()
                combined = combined[~combined.index.duplicated()]
                out = pd.DataFrame({
                    "stock_code": code,
                    "datetime": pd.to_datetime(combined.index),
                    "date": pd.to_datetime(combined.index).date,
                    "open": combined["open"].values,
                    "high": combined["high"].values,
                    "low": combined["low"].values,
                    "close": combined["close"].values,
                    "volume": (combined["volume"] if "volume" in combined.columns else combined["vol"]).astype(int).values,
                })
                all_frames.append(out)
            if (i + 1) % 200 == 0:
                logger.info("  5min progress: %d/%d (%.0fs)", i + 1, len(codes), time.time() - t0)

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

