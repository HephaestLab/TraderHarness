"""Trading tools for agents."""

from __future__ import annotations

from finharness.tools.registry import ToolDef


async def _place_order(context, stock_code: str, action: str, quantity: int = 100, reasoning: str = "", **kwargs) -> dict:
    """Place a buy or sell order."""
    env = context
    if not hasattr(env, "place_order"):
        return {"error": "place_order not available"}
    return await env.place_order(
        agent_id=getattr(env, "agent_id", ""),
        stock_code=stock_code,
        side=action,
        quantity=quantity,
        reasoning=reasoning,
    )


PLACE_ORDER = ToolDef(
    name="place_order",
    description="下单买入或卖出股票",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
            "action": {"type": "string", "enum": ["buy", "sell"], "description": "买入或卖出"},
            "quantity": {"type": "integer", "description": "数量（买入须为100倍数）", "default": 100},
            "reasoning": {"type": "string", "description": "交易理由"},
        },
        "required": ["stock_code", "action"],
    },
    handler=_place_order,
    phase_restricted=["open_window", "close_window"],
)
