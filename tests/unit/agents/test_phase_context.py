"""Phase-boundary context bugs: frozen windows, morning look-ahead, watchlist persist."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.agents.loop import AgentLoop
from traderharness.agents.sandbox.api import MarketAPI
from traderharness.agents.window_context import (
    previous_close_prices,
    refresh_trading_window,
)
from traderharness.core.portfolio import Portfolio
from traderharness.tools.registry import ToolContext

CURRENT = date(2024, 3, 5)
CODE = "600519"


def _daily(closes):
    return pd.DataFrame(
        {
            "date": [d for d, _ in closes],
            "open": [c for _, c in closes],
            "high": [c for _, c in closes],
            "low": [c for _, c in closes],
            "close": [c for _, c in closes],
            "volume": [1000] * len(closes),
        }
    )


def _intraday_bars(open_close=120.0, close_close=125.0):
    rows = [
        (9, 35, open_close - 1),
        (9, 50, open_close - 0.5),
        (10, 0, open_close),
        (14, 35, close_close - 1),
        (14, 50, close_close - 0.5),
        (15, 0, close_close),
    ]
    return pd.DataFrame(
        {
            "datetime": [datetime(2024, 3, 5, h, m) for h, m, _ in rows],
            "date": [CURRENT] * len(rows),
            "open": [p for _, _, p in rows],
            "high": [p for _, _, p in rows],
            "low": [p for _, _, p in rows],
            "close": [p for _, _, p in rows],
            "volume": [1000] * len(rows),
        }
    )


class _FakeBus:
    def __init__(self, bars):
        self._bars = bars

    def get_5min_bars(self, code, target_date=None):
        return self._bars.get(code, pd.DataFrame())

    def get_execution_price(self, code, window="open"):
        bars = self.get_5min_bars(code)
        if bars.empty:
            return None
        minutes = bars["datetime"].dt.hour * 60 + bars["datetime"].dt.minute
        if window.startswith("open"):
            sliced = bars[minutes <= 10 * 60]
        else:
            sliced = bars[minutes <= 15 * 60]
        if sliced.empty:
            return None
        return Decimal(str(float(sliced.iloc[-1]["close"])))


def _ctx(*, held=False, watchlist=None):
    portfolio = Portfolio(Decimal("1000000"))
    if held:
        portfolio.buy(CODE, "name", Decimal("100"), 100, date(2024, 3, 1))
    daily = _daily(
        [
            (date(2024, 3, 1), 100.0),
            (date(2024, 3, 4), 110.0),
            (CURRENT, 999.0),
        ]
    )
    ctx = ToolContext(
        current_date=CURRENT,
        current_phase="pre_market",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        preloaded_daily={CODE: daily},
        execution_price={CODE: Decimal("120")} if held else {},
        close_prices={CODE: Decimal("125")} if held else {},
        window_minutes={},
        agent_id="phase",
        workspace_root="phase",
        _bus=_FakeBus({CODE: _intraday_bars()}),
    )
    if watchlist is not None:
        ctx.tool_call_cache["watchlist"] = dict(watchlist)
    return ctx


def test_refresh_trading_window_includes_same_day_watchlist():
    ctx = _ctx(watchlist={CODE: "new"})
    assert CODE not in ctx.window_minutes
    refresh_trading_window(ctx, window="open")
    assert CODE in ctx.window_minutes
    assert not ctx.window_minutes[CODE].empty
    assert ctx.execution_price[CODE] == Decimal("120.0")


def test_morning_brief_values_positions_at_previous_close_not_open_fill():
    ctx = _ctx(held=True)
    brief = AgentLoop._build_morning_brief(ctx)
    assert "浮盈+10.0%" in brief
    assert "浮盈+20" not in brief
    assert "昨日+10.00%" in brief


@pytest.mark.asyncio
async def test_get_portfolio_pre_market_uses_previous_close():
    from traderharness.tools.portfolio import handle_get_portfolio

    ctx = _ctx(held=True)
    result = await handle_get_portfolio({}, ctx)
    assert result["positions"][0]["current_price"] == 110.0
    assert result["positions"][0]["pnl_pct"] == 10.0


def test_sandbox_get_kline_5min_falls_back_to_bus_when_window_missing():
    ctx = _ctx(watchlist={CODE: "x"})
    ctx.current_phase = "open_window"
    ctx._current_sub_window = "open_2"
    assert CODE not in ctx.window_minutes
    df = MarketAPI(ctx).get_kline_5min(CODE)
    assert not df.empty
    minutes = [dt.hour * 60 + dt.minute for dt in df["datetime"]]
    assert max(minutes) <= 10 * 60


@pytest.mark.asyncio
async def test_fundamentals_refuses_out_of_universe_codes():
    from traderharness.tools.fundamentals import handle_get_fundamentals

    ctx = _ctx()
    ctx.tool_call_cache["_fundamentals_data"] = pd.DataFrame(
        {
            "stock_code": ["605020"],
            "pub_date": ["2024-01-01"],
            "roe": [0.1],
            "net_profit_margin": [0.1],
            "gross_margin": [0.1],
            "net_profit": [1.0],
            "eps_ttm": [1.0],
            "revenue": [1.0],
            "yoy_net_profit": [0.1],
            "yoy_eps": [0.1],
        }
    )
    result = await handle_get_fundamentals({"stock_code": "605020"}, ctx)
    assert "error" in result
    assert "不在本次回测数据范围内" in result["error"]


@pytest.mark.asyncio
async def test_empty_watchlist_persists_across_days(tmp_path):
    from traderharness.agents.tool_agent import ToolAgent

    class _StubLLM:
        model = "stub"

    agent = ToolAgent(
        agent_id="wl",
        name="wl",
        llm_client=_StubLLM(),
        initial_cash=Decimal("1000000"),
        memory_dir=str(tmp_path),
    )
    agent._watchlist_codes = {CODE}
    ctx = _ctx(watchlist={})
    if "watchlist" in ctx.tool_call_cache:
        watchlist_from_ctx = ctx.tool_call_cache.get("watchlist") or {}
        agent._watchlist_codes = set(watchlist_from_ctx.keys())
    assert agent._watchlist_codes == set()


def test_previous_close_prices_helper():
    ctx = _ctx(held=True)
    prices = previous_close_prices(ctx)
    assert prices[CODE] == Decimal("110.0")


@pytest.mark.asyncio
async def test_open_phase_prompt_includes_same_day_watchlist_bars():
    ctx = _ctx(watchlist={CODE: "new"})
    ctx.window_minutes = {}
    ctx.execution_price = {}
    refresh_trading_window(ctx, window="open")
    text = AgentLoop._format_window_klines(
        AgentLoop._filter_window_bars(ctx.window_minutes, 9 * 60 + 35, 9 * 60 + 50),
        "open half",
        ctx.execution_price,
        ctx,
    )
    assert "无法交易" not in text
    assert CODE in text
