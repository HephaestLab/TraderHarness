"""Rebuild per-phase trading focus (watchlist ∪ positions) and safe valuations.

The day-start snapshot of window_minutes / execution_price must not freeze
across phases: pre-market research routinely mutates the watchlist, and
morning valuation must use previous close — never today's open-window fill.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from traderharness.tools.registry import ToolContext


def active_focus_codes(ctx: ToolContext) -> list[str]:
    """Sorted codes the agent is currently focused on (positions ∪ watchlist)."""
    watchlist = ctx.tool_call_cache.get("watchlist") or {}
    return sorted(set(ctx.portfolio.positions.keys()) | set(watchlist.keys()))


def previous_close_prices(ctx: ToolContext) -> dict[str, Decimal]:
    """Mark-to-market prices safe for pre-market: last close before current_date."""
    prices: dict[str, Decimal] = {}
    for code in ctx.portfolio.positions:
        daily = ctx.preloaded_daily.get(code)
        if daily is None or daily.empty:
            continue
        filtered = daily[daily["date"] < ctx.current_date]
        if filtered.empty:
            continue
        prices[code] = Decimal(str(float(filtered.iloc[-1]["close"])))
    return prices


def refresh_trading_window(
    ctx: ToolContext,
    *,
    window: Literal["open", "close"],
) -> None:
    """Rebuild window_minutes and execution_price for the given window.

    Called immediately before each open/close phase so same-day watchlist adds
    and intraday new positions appear in the agent-facing prompt.
    """
    bus = ctx._bus
    codes = active_focus_codes(ctx)
    window_minutes: dict = {}
    prices: dict[str, Decimal] = {}
    if bus is not None:
        for code in codes:
            bars = bus.get_5min_bars(code, ctx.current_date)
            if bars is not None and not bars.empty:
                window_minutes[code] = bars
            price = bus.get_execution_price(code, window)
            if price is not None:
                prices[code] = price
    ctx.window_minutes = window_minutes
    ctx.execution_price = prices
    if window == "close":
        ctx.close_prices = dict(prices)


def code_in_universe(code: str, ctx: ToolContext) -> bool:
    """True when the code has daily bars in this run's preloaded universe."""
    if not code:
        return False
    df = ctx.preloaded_daily.get(code)
    if df is not None and not df.empty:
        return True
    bus = getattr(ctx, "_bus", None)
    if bus is not None and getattr(bus, "market", None) is not None:
        market_df = bus.market.get(code)
        return market_df is not None and not market_df.empty
    return False


def universe_error(code: str) -> dict[str, str]:
    return {"error": f"{code} 不在本次回测数据范围内，无法查询"}
