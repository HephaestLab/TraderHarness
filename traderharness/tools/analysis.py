"""分析工具 — screen_stocks, get_market_overview, get_sector_summary。"""

from __future__ import annotations

import logging

from traderharness.data.stock_registry_loader import get_stock_industry
from traderharness.tools._coerce import safe_int
from traderharness.tools.registry import ToolContext, ToolDefinition

logger = logging.getLogger(__name__)


def build_market_overview(ctx: ToolContext) -> dict:
    """Point-in-time market overview shared by tools and sandbox MarketAPI."""
    sector_data: dict[str, list[float]] = {}
    total_up = 0
    total_down = 0

    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2]
        prev_close = float(prev["close"])
        if prev_close == 0:
            continue
        change = (float(last["close"]) - prev_close) / prev_close * 100
        if change > 0:
            total_up += 1
        elif change < 0:
            total_down += 1

        industry = get_stock_industry(code)
        if industry not in sector_data:
            sector_data[industry] = []
        sector_data[industry].append(change)

    if not sector_data:
        return {"error": "当前交易日无市场数据"}

    sector_avg = {s: sum(v) / len(v) for s, v in sector_data.items() if len(v) >= 3}
    sorted_sectors = sorted(sector_avg.items(), key=lambda x: -x[1])

    return {
        "total_stocks": total_up + total_down,
        "up_count": total_up,
        "down_count": total_down,
        "top_sectors": [
            {"sector": s, "avg_change_pct": round(c, 2)} for s, c in sorted_sectors[:5]
        ],
        "bottom_sectors": [
            {"sector": s, "avg_change_pct": round(c, 2)} for s, c in sorted_sectors[-5:]
        ],
        "total_sectors": len(sorted_sectors),
    }


def build_screen_stocks(ctx: ToolContext, params: dict | None = None) -> dict:
    """Point-in-time stock screen shared by tools and sandbox MarketAPI."""
    params = params or {}
    price_min = params.get("price_min", 0)
    price_max = params.get("price_max", 99999)
    change_pct_min = params.get("change_pct_min")
    change_pct_max = params.get("change_pct_max")
    volume_min = params.get("volume_min", 0)
    industry = params.get("industry", "")
    sort_by = params.get("sort_by", "change_5d")
    max_results = min(params.get("max_results", 10), 30)

    results = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 5:
            continue

        if industry:
            stock_industry = get_stock_industry(code)
            if industry not in stock_industry:
                continue

        last = filtered.iloc[-1]
        close = float(last["close"])
        volume = safe_int(last.get("volume", 0))

        if close < price_min or close > price_max:
            continue
        if volume < volume_min:
            continue

        prev = filtered.iloc[-2]
        prev_close = float(prev["close"])
        change_1d = ((close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0

        if change_pct_min is not None and change_1d < change_pct_min:
            continue
        if change_pct_max is not None and change_1d > change_pct_max:
            continue

        prev_5 = filtered.iloc[-5]
        change_5d = (close - float(prev_5["close"])) / float(prev_5["close"]) * 100

        results.append(
            {
                "code": code,
                "close": round(close, 2),
                "change_1d_pct": round(change_1d, 2),
                "change_5d_pct": round(change_5d, 2),
                "volume": volume,
            }
        )

    sort_key = {"change_5d": "change_5d_pct", "change_1d": "change_1d_pct", "volume": "volume"}.get(
        sort_by, "change_5d_pct"
    )
    results.sort(key=lambda x: (-x[sort_key], x["code"]))

    if not results:
        return {"stocks": [], "total_matched": 0, "hint": "无股票满足筛选条件，建议放宽条件"}

    return {"stocks": results[:max_results], "total_matched": len(results)}


def build_sector_constituents(ctx: ToolContext, sector: str) -> list[dict] | dict:
    """All point-in-time constituents for a sector, or an error dict."""
    if not sector:
        return {"error": "请指定板块名称（如：电力设备、医药生物、金融行业）"}

    stocks = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        stock_industry = get_stock_industry(code)
        if sector not in stock_industry:
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
        return {"error": f"未找到板块「{sector}」或该板块在当前日期无数据"}

    # Secondary key by code so equal change_pct ties stay fingerprint-stable.
    stocks.sort(key=lambda x: (-x["change_pct"], x["code"]))
    return stocks


def build_sector_summary(ctx: ToolContext, sector: str) -> dict:
    """Point-in-time sector summary shared by tools and sandbox MarketAPI."""
    stocks = build_sector_constituents(ctx, sector)
    if isinstance(stocks, dict):
        return stocks

    avg_change = sum(s["change_pct"] for s in stocks) / len(stocks)
    return {
        "sector": sector,
        "avg_change_pct": round(avg_change, 2),
        "stock_count": len(stocks),
        "top_gainers": stocks[:5],
        "top_losers": stocks[-5:] if len(stocks) > 5 else [],
    }


async def handle_get_market_overview(params: dict, ctx: ToolContext) -> dict:
    return build_market_overview(ctx)


async def handle_screen_stocks(params: dict, ctx: ToolContext) -> dict:
    return build_screen_stocks(ctx, params)


async def handle_get_sector_summary(params: dict, ctx: ToolContext) -> dict:
    """获取指定板块内股票详情。"""
    return build_sector_summary(ctx, params.get("sector", ""))


GET_MARKET_OVERVIEW = ToolDefinition(
    name="get_market_overview",
    description="查看全市场概览：涨跌家数、板块涨幅前5/跌幅前5",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_get_market_overview,
)

SCREEN_STOCKS = ToolDefinition(
    name="screen_stocks",
    description="按条件筛选股票：价格、涨跌幅、成交量、行业",
    parameters={
        "type": "object",
        "properties": {
            "price_min": {"type": "number", "description": "最低价格"},
            "price_max": {"type": "number", "description": "最高价格"},
            "change_pct_min": {"type": "number", "description": "最小涨跌幅(%)"},
            "change_pct_max": {"type": "number", "description": "最大涨跌幅(%)"},
            "volume_min": {"type": "integer", "description": "最小成交量"},
            "industry": {"type": "string", "description": "行业名称过滤（如：电力设备）"},
            "sort_by": {
                "type": "string",
                "enum": ["change_5d", "change_1d", "volume"],
                "description": "排序方式，默认按5日涨幅",
            },
            "max_results": {"type": "integer", "description": "最多返回数量，默认10，最大30"},
        },
        "required": [],
    },
    handler=handle_screen_stocks,
)

GET_SECTOR_SUMMARY = ToolDefinition(
    name="get_sector_summary",
    description="查看指定板块详情：板块内股票涨跌幅排名、平均涨幅",
    parameters={
        "type": "object",
        "properties": {
            "sector": {
                "type": "string",
                "description": "板块名称，如：电力设备、医药生物、金融行业",
            },
        },
        "required": ["sector"],
    },
    handler=handle_get_sector_summary,
)
