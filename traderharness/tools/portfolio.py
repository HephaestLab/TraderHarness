"""仓位查询工具 — get_portfolio, get_position。

直接从源项目 backend/agents/agentic/tools/portfolio_tools.py 迁移。
"""

from __future__ import annotations

from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition


def _position_plan(ctx: ToolContext, code: str) -> dict | None:
    plans = ctx.tool_call_cache.get("_position_plans", {})
    plan = plans.get(code)
    if plan is None:
        return None
    return {
        **plan,
        "holding_trading_days": max(0, ctx.day_index - int(plan["entry_day_index"])),
    }


async def handle_get_portfolio(params: dict, ctx: ToolContext) -> dict:
    portfolio = ctx.portfolio
    from traderharness.agents.window_context import previous_close_prices

    current_contract = is_current_contract(getattr(ctx, "tool_contract_version", None))
    price_sources: dict[str, str] = {}
    if ctx.current_phase == "pre_market":
        prices = previous_close_prices(ctx)
        price_sources.update({code: "previous_daily_close" for code in prices})
    else:
        prices = dict(ctx.execution_price)
        price_sources.update({code: "current_visible_window" for code in prices})

    # A stock can be bought from a research result without first entering the
    # phase focus set. In that case ``execution_price`` has no entry until the
    # next window refresh. Fall back to the latest point-in-time-safe close,
    # then acquisition cost, so invested capital is never mistaken for a loss.
    previous = previous_close_prices(ctx)
    for code, pos in portfolio.positions.items():
        if code not in prices and code in previous:
            prices[code] = previous[code]
            price_sources[code] = "previous_daily_close_fallback"
        prices.setdefault(code, pos.avg_cost)
        price_sources.setdefault(code, "average_cost_fallback")

    total_value = float(portfolio.total_value(prices))
    initial = float(ctx.initial_cash)
    return_pct = ((total_value - initial) / initial * 100) if initial > 0 else 0.0

    positions = []
    for code, pos in portfolio.positions.items():
        price = prices.get(code)
        current_price = float(price) if price else float(pos.avg_cost)
        pnl_pct = ((current_price - float(pos.avg_cost)) / float(pos.avg_cost) * 100) if pos.avg_cost else 0
        item = {
            "stock_code": code,
            "quantity": pos.quantity,
            "avg_cost": float(pos.avg_cost),
            "current_price": current_price,
            "pnl_pct": round(pnl_pct, 2),
            "market_value": round(current_price * pos.quantity, 2),
            "position_plan": _position_plan(ctx, code),
        }
        if current_contract:
            item["price_source"] = price_sources.get(code, "unknown")
        positions.append(item)

    result = {
        "cash": round(float(portfolio.cash), 2),
        "total_value": round(total_value, 2),
        "return_pct": round(return_pct, 2),
        "positions": positions,
        "position_count": len(positions),
    }
    if current_contract:
        result["valuation_phase"] = ctx.current_phase
    return result


async def handle_get_position(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    pos = ctx.portfolio.positions.get(code)
    if pos is None:
        return {"error": f"未持有 {code}"}

    current_contract = is_current_contract(getattr(ctx, "tool_contract_version", None))
    if ctx.current_phase == "pre_market":
        from traderharness.agents.window_context import previous_close_prices

        price = previous_close_prices(ctx).get(code)
        price_source = "previous_daily_close"
    else:
        price = ctx.execution_price.get(code)
        price_source = "current_visible_window"
        if price is None and current_contract:
            from traderharness.agents.window_context import previous_close_prices

            price = previous_close_prices(ctx).get(code)
            price_source = "previous_daily_close_fallback"
    current_price = float(price) if price else float(pos.avg_cost)
    if not price:
        price_source = "average_cost_fallback"
    pnl_pct = ((current_price - float(pos.avg_cost)) / float(pos.avg_cost) * 100) if pos.avg_cost else 0
    sellable = pos.sellable_quantity(ctx.current_date)
    plan = _position_plan(ctx, code)

    result = {
        "stock_code": code,
        "quantity": pos.quantity,
        "avg_cost": float(pos.avg_cost),
        "current_price": current_price,
        "pnl_pct": round(pnl_pct, 2),
        "sellable_quantity": sellable,
        "days_held": (ctx.current_date - pos.buy_date).days,
        "holding_trading_days": plan["holding_trading_days"] if plan else None,
        "position_plan": plan,
    }
    if current_contract:
        result["price_source"] = price_source
    return result


GET_PORTFOLIO = ToolDefinition(
    name="get_portfolio",
    description="查看当前持仓和资金状况：现金、总资产、收益率、各持仓详情",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_get_portfolio,
)

GET_POSITION = ToolDefinition(
    name="get_position",
    description="查看某只股票的持仓详情：数量、成本、浮盈、可卖数量等",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_position,
)
