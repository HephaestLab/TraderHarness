"""TDD tests for date anonymization at the agent-facing egress points.

When ctx.date_masker is enabled, every real calendar date that reaches the LLM
must be rendered as a relative offset (D-N / D-N HH:MM / integer column).
When the masker is absent/disabled, behavior is unchanged (bright mode).
"""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.tools.registry import ToolContext
from traderharness.core.portfolio import Portfolio
from traderharness.core.masking import DateMasker
from traderharness.agents.sandbox.api import MarketAPI, NewsAPI
from traderharness.tools.valuation import handle_get_valuation
from traderharness.tools.market import handle_get_kline, handle_get_stock_price


CUR = date(2024, 3, 5)


def _daily():
    return {"600519": pd.DataFrame({
        "date": [date(2024, 3, d) for d in range(1, 6)],
        "open": [1800 + i for i in range(5)],
        "high": [1810 + i for i in range(5)],
        "low": [1790 + i for i in range(5)],
        "close": [1805 + i for i in range(5)],
        "volume": [10000] * 5,
    })}


def _make_ctx(enabled: bool | None) -> ToolContext:
    ctx = ToolContext(
        current_date=CUR,
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily=_daily(),
        agent_id="t",
        workspace_root="t",
    )
    if enabled is not None:
        ctx.date_masker = DateMasker(anchor=CUR, enabled=enabled)
    return ctx


class TestSandboxEgress:
    def test_get_kline_date_column_is_int_offset(self):
        api = MarketAPI(_make_ctx(True))
        df = api.get_kline("600519", days=120)
        assert all(isinstance(v, (int,)) or float(v).is_integer() for v in df["date"])
        assert df["date"].max() == -1  # most recent visible = yesterday

    def test_get_all_daily_date_column_is_int_offset(self):
        api = MarketAPI(_make_ctx(True))
        df = api.get_all_daily(days=20)
        assert df["date"].max() == -1

    def test_get_fundamentals_pub_date_masked(self):
        ctx = _make_ctx(True)
        ctx.tool_call_cache["_fundamentals_data"] = pd.DataFrame({
            "stock_code": ["600519"],
            "pub_date": ["2024-03-01"],
            "roe": [25.0],
        })
        api = MarketAPI(ctx)
        out = api.get_fundamentals("600519")
        assert out["pub_date"] == "D-4"

    def test_announcements_time_masked(self):
        ctx = _make_ctx(True)
        ctx.tool_call_cache["_announcements_data"] = pd.DataFrame({
            "stock_code": ["600519"],
            "announcement_time": [pd.Timestamp("2024-03-04 08:30:00")],
            "title": ["分红预案"],
        })
        api = NewsAPI(ctx)
        out = api.get_announcements("600519", days=30)
        assert out[0]["time"] == "D-1 08:30"

    def test_policy_news_time_masked(self):
        ctx = _make_ctx(True)
        ctx.tool_call_cache["_news_data"] = pd.DataFrame({
            "display_time": [pd.Timestamp("2024-03-02 19:00:00")],
            "content": ["央行宣布降准0.5个百分点"],
        })
        api = NewsAPI(ctx)
        out = api.get_policy_news(days=7)
        assert out[0]["time"] == "D-3 19:00"


class TestValuationEgress:
    @pytest.mark.asyncio
    async def test_valuation_date_masked(self):
        ctx = _make_ctx(True)
        ctx.tool_call_cache["_valuation_data"] = pd.DataFrame({
            "stock_code": ["600519"],
            "date": [date(2024, 3, 4)],
            "pe_ttm": [30.0], "pb_mrq": [8.0], "ps_ttm": [12.0],
            "turn": [1.5], "is_st": [False],
        })
        out = await handle_get_valuation({"stock_code": "600519"}, ctx)
        assert out["date"] == "D-1"

    @pytest.mark.asyncio
    async def test_valuation_date_real_when_disabled(self):
        ctx = _make_ctx(False)
        ctx.tool_call_cache["_valuation_data"] = pd.DataFrame({
            "stock_code": ["600519"],
            "date": [date(2024, 3, 4)],
            "pe_ttm": [30.0], "pb_mrq": [8.0], "ps_ttm": [12.0],
            "turn": [1.5], "is_st": [False],
        })
        out = await handle_get_valuation({"stock_code": "600519"}, ctx)
        assert out["date"] == "2024-03-04"


class TestMarketToolEgress:
    @pytest.mark.asyncio
    async def test_get_kline_uses_d_labels_when_masked(self):
        ctx = _make_ctx(True)
        out = await handle_get_kline({"stock_code": "600519", "days": 20}, ctx)
        labels = [r["day"] for r in out["recent_20"]]
        # most recent visible bar = yesterday = D-1
        assert labels[-1] == "D-1"
        assert all(lbl.startswith("D") for lbl in labels)

    @pytest.mark.asyncio
    async def test_get_kline_keeps_t_labels_when_no_masker(self):
        ctx = _make_ctx(None)
        out = await handle_get_kline({"stock_code": "600519", "days": 20}, ctx)
        labels = [r["day"] for r in out["recent_20"]]
        assert labels[-1] == "T-1"

    @pytest.mark.asyncio
    async def test_get_stock_price_day_masked(self):
        ctx = _make_ctx(True)
        out = await handle_get_stock_price({"stock_code": "600519"}, ctx)
        assert out["day"] == "D-1"
