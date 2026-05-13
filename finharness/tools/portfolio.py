"""Portfolio query tools for agents."""

from __future__ import annotations

from finharness.tools.registry import ToolDef


def _get_portfolio(context, **kwargs) -> dict:
    """Get portfolio overview."""
    env = context
    portfolio = getattr(env, "portfolio", None)
    if portfolio is None:
        return {"error": "portfolio not available"}
    positions = {}
    for code, pos in portfolio.positions.items():
        positions[code] = {
            "quantity": pos.quantity,
            "avg_cost": float(pos.avg_cost),
        }
    return {
        "cash": float(portfolio.cash),
        "positions": positions,
        "total_positions": len(positions),
    }


def _get_position(context, stock_code: str, **kwargs) -> dict:
    """Get position for a specific stock."""
    env = context
    portfolio = getattr(env, "portfolio", None)
    if portfolio is None:
        return {"error": "portfolio not available"}
    pos = portfolio.positions.get(stock_code)
    if pos is None:
        return {"held": False, "stock_code": stock_code}
    return {
        "held": True,
        "stock_code": stock_code,
        "quantity": pos.quantity,
        "avg_cost": float(pos.avg_cost),
    }


GET_PORTFOLIO = ToolDef(
    name="get_portfolio",
    description="查看当前持仓和资金",
    parameters={"type": "object", "properties": {}},
    handler=_get_portfolio,
)

GET_POSITION = ToolDef(
    name="get_position",
    description="查看某只股票的持仓",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
        },
        "required": ["stock_code"],
    },
    handler=_get_position,
)
