"""Market data tools for agents."""

from __future__ import annotations

from finharness.tools.registry import ToolDef


def _get_kline(context, stock_code: str, days: int = 20, **kwargs) -> dict:
    """Get K-line (candlestick) data."""
    env = context
    if not hasattr(env, "get_kline"):
        return {"error": "get_kline not available in this context"}
    return env.get_kline(stock_code, days)


def _get_price(context, stock_code: str, **kwargs) -> dict:
    """Get latest price."""
    env = context
    if not hasattr(env, "get_stock_price"):
        return {"error": "get_stock_price not available"}
    return env.get_stock_price(stock_code)


def _get_stock_info(context, stock_code: str, **kwargs) -> dict:
    """Get stock information."""
    env = context
    if not hasattr(env, "get_stock_info"):
        return {"error": "get_stock_info not available"}
    return env.get_stock_info(stock_code)


GET_KLINE = ToolDef(
    name="get_kline",
    description="获取股票日K线数据",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
            "days": {"type": "integer", "description": "天数", "default": 20},
        },
        "required": ["stock_code"],
    },
    handler=_get_kline,
)

GET_PRICE = ToolDef(
    name="get_stock_price",
    description="获取股票最新价格",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
        },
        "required": ["stock_code"],
    },
    handler=_get_price,
)

GET_STOCK_INFO = ToolDef(
    name="get_stock_info",
    description="获取股票基本信息",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
        },
        "required": ["stock_code"],
    },
    handler=_get_stock_info,
)
