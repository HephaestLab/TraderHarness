"""仓位查询工具 — get_portfolio, get_position。

直接从源项目 backend/agents/agentic/tools/portfolio_tools.py 迁移。
"""

from __future__ import annotations

from finharness.tools.registry import ToolDefinition, ToolContext


async def handle_get_portfolio(params: dict, ctx: ToolContext) -> dict:
    portfolio = ctx.portfolio
    prices = ctx.execution_price if ctx.execution_price else {}

    total_value = float(portfolio.total_value(prices)) if prices else float(portfolio.cash)
    initial = float(ctx.initial_cash)
    return_pct = ((total_value - initial) / initial * 100) if initial > 0 else 0.0

    positions = []
    for code, pos in portfolio.positions.items():
        price = prices.get(code)
        current_price = float(price) if price else float(pos.avg_cost)
        pnl_pct = ((current_price - float(pos.avg_cost)) / float(pos.avg_cost) * 100) if pos.avg_cost else 0
        positions.append({
            "stock_code": code,
            "quantity": pos.quantity,
            "avg_cost": float(pos.avg_cost),
            "current_price": current_price,
            "pnl_pct": round(pnl_pct, 2),
            "market_value": round(current_price * pos.quantity, 2),
        })

    return {
        "cash": round(float(portfolio.cash), 2),
        "total_value": round(total_value, 2),
        "return_pct": round(return_pct, 2),
        "positions": positions,
        "position_count": len(positions),
    }


async def handle_get_position(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    pos = ctx.portfolio.positions.get(code)
    if pos is None:
        return {"error": f"未持有 {code}"}

    price = ctx.execution_price.get(code)
    current_price = float(price) if price else float(pos.avg_cost)
    pnl_pct = ((current_price - float(pos.avg_cost)) / float(pos.avg_cost) * 100) if pos.avg_cost else 0
    sellable = pos.sellable_quantity(ctx.current_date)

    return {
        "stock_code": code,
        "quantity": pos.quantity,
        "avg_cost": float(pos.avg_cost),
        "buy_date": str(pos.buy_date),
        "current_price": current_price,
        "pnl_pct": round(pnl_pct, 2),
        "sellable_quantity": sellable,
        "days_held": (ctx.current_date - pos.buy_date).days,
    }


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
