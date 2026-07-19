"""估值查询工具 — get_valuation，返回 PE/PB/换手率。"""

from __future__ import annotations

from traderharness.tools.registry import ToolContext, ToolDefinition


async def handle_get_valuation(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    if not code:
        return {"error": "stock_code 不能为空"}
    from traderharness.agents.window_context import code_in_universe, universe_error

    if not code_in_universe(code, ctx):
        return universe_error(code)

    valuation_data = ctx.tool_call_cache.get("_valuation_data")
    if valuation_data is None:
        return {"error": "估值数据未加载"}

    stock_data = valuation_data[
        (valuation_data["stock_code"] == code) & (valuation_data["date"] < ctx.current_date)
    ]
    if stock_data.empty:
        return {"error": f"{code} 无估值数据"}

    latest = stock_data.iloc[-1]

    masker = getattr(ctx, "date_masker", None)
    date_label = masker.mask_date(latest["date"]) if masker is not None else str(latest["date"])

    result = {
        "stock_code": code,
        "date": date_label,
        "pe_ttm": _safe_round(latest.get("pe_ttm")),
        "pb_mrq": _safe_round(latest.get("pb_mrq")),
        "ps_ttm": _safe_round(latest.get("ps_ttm")),
        "turnover_pct": _safe_round(latest.get("turn")),
        "is_st": bool(latest.get("is_st", False)),
    }

    # Add recent average turnover (5-day)
    if len(stock_data) >= 5:
        recent_turn = stock_data.tail(5)["turn"].mean()
        result["avg_turnover_5d_pct"] = _safe_round(recent_turn)

    return result


def _safe_round(val, digits=2):
    if val is None or val != val:  # NaN
        return None
    return round(float(val), digits)


GET_VALUATION = ToolDefinition(
    name="get_valuation",
    description="查询股票估值指标：市盈率(PE_TTM)、市净率(PB)、市销率(PS)、换手率。也可用于判断是否ST股。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_valuation,
)
