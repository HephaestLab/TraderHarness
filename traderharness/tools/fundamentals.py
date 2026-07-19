"""基本面查询工具 — get_fundamentals，按 pub_date 历史对齐。"""

from __future__ import annotations

from traderharness.tools.registry import ToolContext, ToolDefinition


async def handle_get_fundamentals(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    if not code:
        return {"error": "stock_code 不能为空"}
    from traderharness.agents.window_context import code_in_universe, universe_error

    if not code_in_universe(code, ctx):
        return universe_error(code)

    fundamentals = ctx.tool_call_cache.get("_fundamentals_data")
    if fundamentals is None:
        return {"error": "基本面数据未加载"}

    stock_data = fundamentals[fundamentals["stock_code"] == code]
    if stock_data.empty:
        return {"error": f"{code} 无基本面数据"}

    visible = stock_data[stock_data["pub_date"] <= str(ctx.current_date)]
    if visible.empty:
        return {"error": f"{code} 在当前交易日之前无已发布的财务数据"}

    latest = visible.iloc[-1]
    return {
        "stock_code": code,
        "roe": latest.get("roe"),
        "net_profit_margin": latest.get("net_profit_margin"),
        "gross_margin": latest.get("gross_margin"),
        "net_profit": latest.get("net_profit"),
        "eps_ttm": latest.get("eps_ttm"),
        "revenue": latest.get("revenue"),
        "yoy_net_profit": latest.get("yoy_net_profit"),
        "yoy_eps": latest.get("yoy_eps"),
    }


GET_FUNDAMENTALS = ToolDefinition(
    name="get_fundamentals",
    description="查询股票基本面：ROE、净利率、毛利率、净利润、EPS、营收及同比增速。数据按财报发布日期对齐，只返回当前已公开的最新数据。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_fundamentals,
)
