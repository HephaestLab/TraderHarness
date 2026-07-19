"""NewsDataManager — loads announcements + news into memory at engine startup."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from traderharness.paths import dataset_dir

logger = logging.getLogger(__name__)

DATASET_DIR = dataset_dir()

POLICY_KEYWORDS = ["央行", "证监会", "国务院", "财政部", "银保监", "发改委", "人民银行"]


class NewsDataManager:
    """Manages announcement and news data for the backtest lifecycle."""

    # get_announcements tool allows max 90 days lookback
    _ANN_LOOKBACK_DAYS = 90
    # get_news tool allows max 3 days lookback
    _NEWS_LOOKBACK_DAYS = 3

    def __init__(self, dataset_dir: Path | None = None, templated: bool = False) -> None:
        self._dir = dataset_dir or DATASET_DIR
        self._templated = templated
        self._announcements: pd.DataFrame = pd.DataFrame()
        self._news: pd.DataFrame = pd.DataFrame()

    def _select_text_path(self, canonical_name: str, templated_name: str) -> Path:
        canonical = self._dir / canonical_name
        templated = self._dir / templated_name
        if not self._templated or not templated.exists():
            return canonical
        if not canonical.exists() or templated.stat().st_mtime >= canonical.stat().st_mtime:
            return templated
        logger.warning(
            "%s is stale; loading canonical %s and applying runtime masking",
            templated.name,
            canonical.name,
        )
        return canonical

    def load(self, start_date: date | None = None, end_date: date | None = None) -> None:
        """Load news data. If date range provided, only loads relevant window.

        Safety margins:
        - Announcements: start_date - 90 days (max tool lookback)
        - News: start_date - 30 days (max tool lookback)
        """
        from datetime import timedelta

        ann_path = self._select_text_path(
            "announcements.parquet",
            "announcements_templated.parquet",
        )
        if ann_path.exists():
            if start_date:
                load_from = start_date - timedelta(days=self._ANN_LOOKBACK_DAYS)
                import pyarrow as pa
                import pyarrow.dataset as ds

                dataset = ds.dataset(ann_path, format="parquet")
                filters = ds.field("announcement_time") >= pa.scalar(pd.Timestamp(load_from))
                if end_date:
                    filters = filters & (
                        ds.field("announcement_time") <= pa.scalar(pd.Timestamp(end_date))
                    )
                table = dataset.to_table(filter=filters)
                self._announcements = table.to_pandas()
            else:
                self._announcements = pd.read_parquet(ann_path)

            if "announcement_time" in self._announcements.columns:
                self._announcements["announcement_time"] = pd.to_datetime(
                    self._announcements["announcement_time"]
                )
            logger.info("Announcements loaded: %d rows", len(self._announcements))
        else:
            logger.warning("announcements.parquet not found at %s", ann_path)

        news_path = self._select_text_path(
            "news_cls.parquet",
            "news_cls_templated.parquet",
        )
        if news_path.exists():
            if start_date:
                load_from = start_date - timedelta(days=self._NEWS_LOOKBACK_DAYS)
                import pyarrow as pa
                import pyarrow.dataset as ds

                dataset = ds.dataset(news_path, format="parquet")
                filters = ds.field("display_time") >= pa.scalar(pd.Timestamp(load_from))
                if end_date:
                    filters = filters & (
                        ds.field("display_time") <= pa.scalar(pd.Timestamp(end_date))
                    )
                table = dataset.to_table(filter=filters)
                self._news = table.to_pandas()
            else:
                self._news = pd.read_parquet(news_path)

            if "ctime" in self._news.columns and "display_time" not in self._news.columns:
                self._news["display_time"] = pd.to_datetime(self._news["ctime"], unit="s")
            elif "display_time" in self._news.columns:
                self._news["display_time"] = pd.to_datetime(self._news["display_time"])
            logger.info("News loaded: %d rows", len(self._news))
        else:
            logger.warning("news_cls.parquet not found at %s", news_path)

    @property
    def announcements(self) -> pd.DataFrame:
        return self._announcements

    @property
    def news(self) -> pd.DataFrame:
        return self._news

    def get_p0_announcements(
        self,
        target_codes: set[str],
        prev_close: datetime,
        today_open: datetime,
    ) -> list[dict]:
        """P0: announcements for holdings + watchlist between prev close and today open."""
        if self._announcements.empty or not target_codes:
            return []

        mask = (
            self._announcements["stock_code"].isin(target_codes)
            & (self._announcements["announcement_time"] >= prev_close)
            & (self._announcements["announcement_time"] < today_open)
        )
        filtered = self._announcements[mask].sort_values("announcement_time", ascending=False)

        results = []
        for _, row in filtered.head(15).iterrows():
            results.append(
                {
                    "stock_code": row["stock_code"],
                    "title": row["title"],
                    "time": str(row["announcement_time"]),
                }
            )
        return results

    def get_p1_policy_news(
        self,
        prev_close: datetime,
        today_open: datetime,
    ) -> list[dict]:
        """P1: national-level policy news between prev close and today open."""
        if self._news.empty:
            return []

        mask = (self._news["display_time"] >= prev_close) & (
            self._news["display_time"] < today_open
        )
        time_filtered = self._news[mask]

        if time_filtered.empty:
            return []

        keyword_mask = time_filtered["content"].str.contains("|".join(POLICY_KEYWORDS), na=False)
        policy = time_filtered[keyword_mask].sort_values("display_time", ascending=False)

        results = []
        for _, row in policy.iterrows():
            results.append(
                {
                    "time": str(row["display_time"]),
                    "content": str(row["content"])[:200],
                    "level": row.get("level", ""),
                }
            )
        return results

    def get_window_news(
        self,
        target_codes: set[str],
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[list[dict], list[dict]]:
        """Get P0 announcements and P1 policy for a trading window."""
        p0 = []
        if not self._announcements.empty and target_codes:
            mask = (
                self._announcements["stock_code"].isin(target_codes)
                & (self._announcements["announcement_time"] >= window_start)
                & (self._announcements["announcement_time"] < window_end)
            )
            for _, row in self._announcements[mask].head(10).iterrows():
                p0.append(
                    {
                        "stock_code": row["stock_code"],
                        "title": row["title"],
                        "time": str(row["announcement_time"]),
                    }
                )

        p1 = []
        if not self._news.empty:
            mask = (self._news["display_time"] >= window_start) & (
                self._news["display_time"] < window_end
            )
            time_filtered = self._news[mask]
            if not time_filtered.empty:
                keyword_mask = time_filtered["content"].str.contains(
                    "|".join(POLICY_KEYWORDS), na=False
                )
                policy = time_filtered[keyword_mask].sort_values(
                    "display_time", ascending=False
                )
                for _, row in policy.head(5).iterrows():
                    p1.append(
                        {
                            "time": str(row["display_time"]),
                            "content": str(row["content"])[:200],
                        }
                    )

        return p0, p1
