"""分析工具 — screen_stocks, get_market_overview, get_sector_summary。

从源项目 backend/agents/agentic/tools/analysis_tools.py 迁移。
"""

from __future__ import annotations

import logging

from finharness.tools.registry import ToolDefinition, ToolContext

logger = logging.getLogger(__name__)


async def handle_get_market_overview(params: dict, ctx: ToolContext) -> dict:
    sector_data: dict[str, list[dict]] = {}
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2]
        prev_close = float(prev["close"])
        change = ((float(last["close"]) - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        sector = "default"
        if sector not in sector_data:
            sector_data[sector] = []
        sector_data[sector].append({"code": code, "change_pct": round(change, 2)})

    if not sector_data:
        return {"date": str(ctx.current_date), "sectors": [], "total_stocks": 0}

    sorted_sectors = sorted(sector_data.items(), key=lambda x: -sum(s["change_pct"] for s in x[1]) / len(x[1]))
    return {
        "date": str(ctx.current_date),
        "top_sectors": [{"sector": s, "avg_change_pct": round(sum(st["change_pct"] for st in stocks) / len(stocks), 2)} for s, stocks in sorted_sectors[:5]],
        "bottom_sectors": [{"sector": s, "avg_change_pct": round(sum(st["change_pct"] for st in stocks) / len(stocks), 2)} for s, stocks in sorted_sectors[-5:]],
        "total_sectors": len(sorted_sectors),
    }


async def handle_screen_stocks(params: dict, ctx: ToolContext) -> dict:
    price_min = params.get("price_min", 0)
    price_max = params.get("price_max", 99999)
    max_results = min(params.get("max_results", 10), 20)

    results = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 5:
            continue
        last = filtered.iloc[-1]
        close = float(last["close"])
        if close < price_min or close > price_max:
            continue
        prev_5 = filtered.iloc[-5]
        change_5d = (close - float(prev_5["close"])) / float(prev_5["close"]) * 100
        results.append({"code": code, "close": round(close, 2), "change_5d_pct": round(change_5d, 2)})

    results.sort(key=lambda x: -x["change_5d_pct"])
    return {"stocks": results[:max_results], "total_matched": len(results)}


GET_MARKET_OVERVIEW = ToolDefinition(
    name="get_market_overview",
    description="查看市场/板块全局概览",
    parameters={"type": "object", "properties": {"sector": {"type": "string", "description": "可选，只看某个板块"}}, "required": []},
    handler=handle_get_market_overview,
)

SCREEN_STOCKS = ToolDefinition(
    name="screen_stocks",
    description="按条件筛选股票",
    parameters={
        "type": "object",
        "properties": {
            "price_min": {"type": "number", "description": "最低价格"},
            "price_max": {"type": "number", "description": "最高价格"},
            "max_results": {"type": "integer", "description": "最多返回数量，默认10"},
        },
        "required": [],
    },
    handler=handle_screen_stocks,
)


async def handle_get_sector_summary(params: dict, ctx: ToolContext) -> dict:
    """获取板块内股票详情。"""
    # Without industry data, group by price range as proxy
    stocks = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2]
        close = float(last["close"])
        prev_close = float(prev["close"])
        change = ((close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        stocks.append({"code": code, "close": round(close, 2), "change_pct": round(change, 2)})

    if not stocks:
        return {"error": "无数据"}

    stocks.sort(key=lambda x: -x["change_pct"])
    avg_change = sum(s["change_pct"] for s in stocks) / len(stocks)
    return {
        "avg_change_pct": round(avg_change, 2),
        "stocks": stocks[:20],
        "top_gainers": stocks[:3],
        "top_losers": stocks[-3:] if len(stocks) > 3 else [],
        "total": len(stocks),
    }


GET_SECTOR_SUMMARY = ToolDefinition(
    name="get_sector_summary",
    description="查看板块详情：板块内股票涨跌幅排名",
    parameters={
        "type": "object",
        "properties": {
            "sector": {"type": "string", "description": "板块名称"},
        },
        "required": ["sector"],
    },
    handler=handle_get_sector_summary,
)
