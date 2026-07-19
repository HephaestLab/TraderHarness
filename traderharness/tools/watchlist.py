"""自选股工具 — Agent 可以追踪特定股票，披露在晨报中。"""

from __future__ import annotations

from traderharness.tools.registry import ToolContext, ToolDefinition


async def handle_add_watchlist(params: dict, ctx: ToolContext) -> dict:
    """添加股票到自选股列表。"""
    code = params.get("stock_code", "")
    reason = params.get("reason", "")
    if not code:
        return {"error": "stock_code 不能为空"}

    if not hasattr(ctx, "_watchlist"):
        ctx._watchlist = {}
    watchlist = ctx.tool_call_cache.setdefault("watchlist", {})
    watchlist[code] = reason
    return {"success": True, "stock_code": code, "reason": reason, "total_watching": len(watchlist)}


async def handle_remove_watchlist(params: dict, ctx: ToolContext) -> dict:
    """从自选股列表移除。"""
    code = params.get("stock_code", "")
    watchlist = ctx.tool_call_cache.get("watchlist", {})
    if code in watchlist:
        del watchlist[code]
        return {"success": True, "removed": code}
    return {"error": f"{code} 不在自选股列表中"}


async def handle_get_watchlist(params: dict, ctx: ToolContext) -> dict:
    """查看自选股列表及其最新行情。"""
    watchlist = ctx.tool_call_cache.get("watchlist", {})
    if not watchlist:
        return {"watchlist": [], "count": 0}

    items = []
    for code, reason in watchlist.items():
        info = {"stock_code": code, "reason": reason}
        df = ctx.preloaded_daily.get(code)
        if df is not None and not df.empty:
            filtered = df[df["date"] < ctx.current_date]
            if not filtered.empty:
                last = filtered.iloc[-1]
                info["close"] = round(float(last["close"]), 2)
                if len(filtered) >= 2:
                    prev = filtered.iloc[-2]
                    change = (
                        (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100
                    )
                    info["change_pct"] = round(change, 2)
        items.append(info)

    return {"watchlist": items, "count": len(items)}


ADD_WATCHLIST = ToolDefinition(
    name="add_watchlist",
    description="添加股票到自选股列表。自选股会在每日晨报中显示最新行情。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
            "reason": {"type": "string", "description": "关注理由（可选）"},
        },
        "required": ["stock_code"],
    },
    handler=handle_add_watchlist,
)

REMOVE_WATCHLIST = ToolDefinition(
    name="remove_watchlist",
    description="从自选股列表移除股票",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码"},
        },
        "required": ["stock_code"],
    },
    handler=handle_remove_watchlist,
)

GET_WATCHLIST = ToolDefinition(
    name="get_watchlist",
    description="查看自选股列表及其最新行情",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_get_watchlist,
)
