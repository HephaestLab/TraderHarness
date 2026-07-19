"""Entity masking coverage across tool, sandbox, and prompt egress."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.agents.loop import AgentLoop
from traderharness.agents.sandbox.api import MarketAPI, NewsAPI, PortfolioAPI
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.portfolio import Portfolio
from traderharness.tools.registry import ToolContext, ToolDefinition, ToolRegistry

CURRENT = date(2024, 3, 5)
REAL = "600519"
OTHER = "600000"


def _daily():
    rows = pd.DataFrame(
        {
            "date": [date(2024, 3, day) for day in range(1, 6)],
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [10_000] * 5,
        }
    )
    return {REAL: rows.copy(), OTHER: rows.copy()}


def _context() -> ToolContext:
    portfolio = Portfolio(Decimal("1000000"))
    portfolio.buy(REAL, "贵州茅台", Decimal("100"), 100, date(2024, 3, 1))
    ctx = ToolContext(
        current_date=CURRENT,
        current_phase="pre_market",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        preloaded_daily=_daily(),
        execution_price={REAL: Decimal("100")},
        agent_id="masked",
        workspace_root="masked",
    )
    ctx.entity_masker = EntityMasker(
        [REAL, OTHER],
        names={REAL: "贵州茅台", OTHER: "浦发银行"},
        aliases={REAL: ["茅台"]},
        seed=1,
    )
    return ctx


@pytest.mark.asyncio
async def test_get_stock_info_refuses_codes_outside_backtest_universe():
    """A real registry name for an out-of-universe code must never be emitted.

    The masker's alias map only covers in-universe codes, so if the handler
    consulted the full packaged registry for any other code, the real company
    name would bypass masking (observed leak: 605020 -> 永和股份).
    """
    from traderharness.tools.market import GET_STOCK_INFO

    ctx = _context()
    registry = ToolRegistry()
    registry.register(GET_STOCK_INFO)

    result = await registry.execute("get_stock_info", {"stock_code": "605020"}, ctx)

    assert "error" in result
    assert "永和股份" not in str(result)


@pytest.mark.asyncio
async def test_get_stock_info_masks_in_universe_name():
    from traderharness.tools.market import GET_STOCK_INFO

    ctx = _context()
    pseudo = ctx.entity_masker.mask_code(REAL)
    registry = ToolRegistry()
    registry.register(GET_STOCK_INFO)

    result = await registry.execute("get_stock_info", {"stock_code": pseudo}, ctx)

    assert result.get("stock_code") == pseudo
    assert "贵州茅台" not in str(result)


@pytest.mark.asyncio
async def test_registry_unmasks_arguments_and_masks_nested_result():
    ctx = _context()
    pseudo = ctx.entity_masker.mask_code(REAL)
    seen = {}

    async def handler(params, _ctx):
        seen.update(params)
        return {
            "stock_code": params["stock_code"],
            "name": "贵州茅台",
            "nested": [{"message": "贵州茅台600519完成"}],
        }

    registry = ToolRegistry()
    registry.register(ToolDefinition("probe", "", {}, handler))
    result = await registry.execute("probe", {"stock_code": pseudo}, ctx)

    assert seen["stock_code"] == REAL
    assert result["stock_code"] == pseudo
    assert "贵州茅台" not in str(result)


def test_sandbox_market_api_accepts_pseudo_code_and_masks_all_market_codes():
    ctx = _context()
    pseudo = ctx.entity_masker.mask_code(REAL)
    api = MarketAPI(ctx)

    assert not api.get_kline(pseudo).empty
    assert set(api.get_stock_list()) == {
        ctx.entity_masker.mask_code(REAL),
        ctx.entity_masker.mask_code(OTHER),
    }
    all_daily = api.get_all_daily()
    assert set(all_daily["stock_code"]) == set(api.get_stock_list())


def test_sandbox_fundamentals_round_trip_uses_pseudo_code():
    ctx = _context()
    ctx.tool_call_cache["_fundamentals_data"] = pd.DataFrame(
        {
            "stock_code": [REAL],
            "stock_name": ["贵州茅台"],
            "pub_date": ["2024-03-01"],
            "roe": [25.0],
        }
    )
    pseudo = ctx.entity_masker.mask_code(REAL)

    result = MarketAPI(ctx).get_fundamentals(pseudo)

    assert result["stock_code"] == pseudo
    assert "贵州茅台" not in str(result)


def test_sandbox_portfolio_and_news_do_not_leak_identity():
    ctx = _context()
    ctx.tool_call_cache["_announcements_data"] = pd.DataFrame(
        {
            "stock_code": [REAL],
            "stock_name": ["贵州茅台"],
            "announcement_time": [pd.Timestamp("2024-03-04 08:30:00")],
            "title": ["贵州茅台年度分红公告"],
        }
    )
    pseudo = ctx.entity_masker.mask_code(REAL)

    positions = PortfolioAPI(ctx).get_positions()
    announcements = NewsAPI(ctx).get_announcements(pseudo)

    assert positions[0]["stock_code"] == pseudo
    assert "贵州茅台" not in str(announcements)
    assert announcements


def test_morning_brief_masks_positions_actions_announcements_and_watchlist():
    ctx = _context()
    pseudo = ctx.entity_masker.mask_code(REAL)
    ctx.tool_call_cache["_corporate_actions"] = [
        {"stock_code": REAL, "description": "贵州茅台现金分红"}
    ]
    ctx.tool_call_cache["_p0_announcements"] = [
        {
            "stock_code": REAL,
            "title": "贵州茅台年度报告",
            "time": "2024-03-04 08:30:00",
        }
    ]
    ctx.tool_call_cache["watchlist"] = {REAL: "关注茅台估值"}

    brief = AgentLoop._build_morning_brief(ctx)

    assert pseudo in brief
    assert REAL not in brief
    assert "贵州茅台" not in brief
    assert "茅台" not in brief


def test_window_kline_text_masks_real_code():
    ctx = _context()
    pseudo = ctx.entity_masker.mask_code(REAL)
    bars = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2024-03-05 09:35:00")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [1000],
        }
    )

    text = AgentLoop._format_window_klines({REAL: bars}, "窗口", ctx=ctx)

    assert pseudo in text
    assert REAL not in text
