"""TDD tests for NewsDataManager — P0 announcements + P1 policy filtering."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from traderharness.data.news_data_manager import NewsDataManager, POLICY_KEYWORDS


@pytest.fixture
def sample_announcements(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "stock_code": ["600519", "600519", "000001", "300750", "600519"],
        "stock_name": ["贵州茅台", "贵州茅台", "平安银行", "宁德时代", "贵州茅台"],
        "title": [
            "2023年年度报告",
            "关于高管增持的公告",
            "2023年第四季度报告",
            "关于新建产能的公告",
            "2024年第一季度报告",
        ],
        "announcement_time": pd.to_datetime([
            "2024-03-03 20:30:00",
            "2024-03-04 08:00:00",
            "2024-03-03 21:00:00",
            "2024-03-05 07:00:00",
            "2024-03-10 19:00:00",
        ]),
        "pdf_url": [""] * 5,
        "ann_type": [None] * 5,
    })
    path = tmp_path / "announcements.parquet"
    df.to_parquet(path, index=False)
    return tmp_path


@pytest.fixture
def sample_news(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "title": ["央行降准", "特斯拉涨", "证监会新规", "苹果发布", "国务院会议"],
        "content": [
            "央行决定下调存款准备金率0.5个百分点",
            "特斯拉股价创新高",
            "证监会发布关于加强退市制度的新规",
            "苹果公司发布最新产品",
            "国务院常务会议研究经济形势",
        ],
        "ctime": [
            int(datetime(2024, 3, 3, 16, 0).timestamp()),
            int(datetime(2024, 3, 3, 17, 0).timestamp()),
            int(datetime(2024, 3, 4, 7, 0).timestamp()),
            int(datetime(2024, 3, 4, 8, 0).timestamp()),
            int(datetime(2024, 3, 5, 6, 0).timestamp()),
        ],
        "display_time": pd.to_datetime([
            "2024-03-03 16:00:00",
            "2024-03-03 17:00:00",
            "2024-03-04 07:00:00",
            "2024-03-04 08:00:00",
            "2024-03-05 06:00:00",
        ]),
        "level": ["A", "C", "A", "C", "A"],
        "tags": [""] * 5,
        "stock_list": [""] * 5,
    })
    path = tmp_path / "news_cls.parquet"
    df.to_parquet(path, index=False)
    return tmp_path


class TestNewsDataManagerLoad:
    def test_loads_announcements(self, sample_announcements):
        mgr = NewsDataManager(dataset_dir=sample_announcements)
        mgr.load()
        assert len(mgr.announcements) == 5

    def test_loads_news(self, sample_news):
        mgr = NewsDataManager(dataset_dir=sample_news)
        mgr.load()
        assert len(mgr.news) == 5

    def test_missing_files_no_crash(self, tmp_path):
        mgr = NewsDataManager(dataset_dir=tmp_path)
        mgr.load()
        assert mgr.announcements.empty
        assert mgr.news.empty


class TestP0Announcements:
    def test_filters_by_target_codes(self, sample_announcements):
        mgr = NewsDataManager(dataset_dir=sample_announcements)
        mgr.load()
        prev_close = datetime(2024, 3, 3, 15, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p0_announcements({"600519"}, prev_close, today_open)
        assert len(results) == 2
        assert all(r["stock_code"] == "600519" for r in results)

    def test_excludes_unrelated_stocks(self, sample_announcements):
        mgr = NewsDataManager(dataset_dir=sample_announcements)
        mgr.load()
        prev_close = datetime(2024, 3, 3, 15, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p0_announcements({"000001"}, prev_close, today_open)
        assert len(results) == 1
        assert results[0]["stock_code"] == "000001"

    def test_empty_target_codes_returns_empty(self, sample_announcements):
        mgr = NewsDataManager(dataset_dir=sample_announcements)
        mgr.load()
        prev_close = datetime(2024, 3, 3, 15, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p0_announcements(set(), prev_close, today_open)
        assert results == []

    def test_time_window_filtering(self, sample_announcements):
        mgr = NewsDataManager(dataset_dir=sample_announcements)
        mgr.load()
        # Window that only catches the 08:00 announcement
        prev_close = datetime(2024, 3, 4, 7, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p0_announcements({"600519"}, prev_close, today_open)
        assert len(results) == 1
        assert "高管增持" in results[0]["title"]


class TestP1PolicyNews:
    def test_filters_policy_keywords(self, sample_news):
        mgr = NewsDataManager(dataset_dir=sample_news)
        mgr.load()
        prev_close = datetime(2024, 3, 3, 15, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p1_policy_news(prev_close, today_open)
        # Should match: 央行降准(16:00), 证监会新规(07:00)
        assert len(results) == 2
        contents = " ".join(r["content"] for r in results)
        assert "央行" in contents
        assert "证监会" in contents

    def test_excludes_non_policy(self, sample_news):
        mgr = NewsDataManager(dataset_dir=sample_news)
        mgr.load()
        prev_close = datetime(2024, 3, 3, 15, 0)
        today_open = datetime(2024, 3, 4, 9, 30)
        results = mgr.get_p1_policy_news(prev_close, today_open)
        contents = " ".join(r["content"] for r in results)
        assert "特斯拉" not in contents
        assert "苹果" not in contents

    def test_respects_time_window(self, sample_news):
        mgr = NewsDataManager(dataset_dir=sample_news)
        mgr.load()
        # Only 国务院会议 is at 2024-03-05 06:00
        prev_close = datetime(2024, 3, 4, 15, 0)
        today_open = datetime(2024, 3, 5, 9, 30)
        results = mgr.get_p1_policy_news(prev_close, today_open)
        assert len(results) == 1
        assert "国务院" in results[0]["content"]


class TestWindowNews:
    def test_returns_both_p0_and_p1(self, tmp_path):
        # Create both files in one directory
        ann_df = pd.DataFrame({
            "stock_code": ["600519"],
            "stock_name": ["贵州茅台"],
            "title": ["关于高管增持的公告"],
            "announcement_time": pd.to_datetime(["2024-03-04 08:00:00"]),
            "pdf_url": [""],
            "ann_type": [None],
        })
        ann_df.to_parquet(tmp_path / "announcements.parquet", index=False)

        news_df = pd.DataFrame({
            "id": [1],
            "title": ["证监会新规"],
            "content": ["证监会发布关于加强退市制度的新规"],
            "ctime": [int(datetime(2024, 3, 4, 7, 0).timestamp())],
            "display_time": pd.to_datetime(["2024-03-04 07:00:00"]),
            "level": ["A"],
            "tags": [""],
            "stock_list": [""],
        })
        news_df.to_parquet(tmp_path / "news_cls.parquet", index=False)

        mgr = NewsDataManager(dataset_dir=tmp_path)
        mgr.load()
        start = datetime(2024, 3, 4, 7, 0)
        end = datetime(2024, 3, 4, 9, 30)
        p0, p1 = mgr.get_window_news({"600519"}, start, end)
        assert len(p0) >= 1  # 600519 announcement at 08:00
        assert len(p1) >= 1  # 证监会新规 at 07:00
