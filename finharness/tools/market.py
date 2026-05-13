"""市场数据工具 — get_kline, get_stock_price, get_stock_info。

直接从源项目 backend/agents/agentic/tools/market_tools.py 迁移。
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from finharness.tools.registry import ToolDefinition, ToolContext

logger = logging.getLogger(__name__)


async def _ensure_daily_data(code: str, ctx: ToolContext) -> pd.DataFrame | None:
    """确保日K数据已加载。优先用 bus，否则返回 preloaded。"""
    if code in ctx.preloaded_daily:
        return ctx.preloaded_daily[code]

    if ctx._bus is not None:
        df = await ctx._bus.get_daily_bars(code, days=250)
        if df is not None and not df.empty:
            ctx.preloaded_daily[code] = df
            return df
        return None

    return None


async def handle_get_kline(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    days = min(params.get("days", 20), 120)

    df = await _ensure_daily_data(code, ctx)
    if df is None or df.empty:
        return {"error": f"无法获取 {code} 的行情数据"}

    filtered = df[df["date"] < ctx.current_date].tail(days)
    if filtered.empty:
        return {"error": f"{code} 在 {ctx.current_date} 之前无数据"}

    records = []
    for _, row in filtered.iterrows():
        records.append({
            "date": str(row["date"]),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row.get("volume", 0)),
        })

    return {"stock_code": code, "count": len(records), "data": records}


async def handle_get_stock_price(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")

    df = await _ensure_daily_data(code, ctx)
    if df is None or df.empty:
        return {"error": f"无法获取 {code} 的行情数据"}

    filtered = df[df["date"] < ctx.current_date]
    if filtered.empty:
        return {"error": f"{code} 在 {ctx.current_date} 之前无数据"}

    last = filtered.iloc[-1]
    prev = filtered.iloc[-2] if len(filtered) >= 2 else last
    change_pct = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100

    return {
        "stock_code": code,
        "date": str(last["date"]),
        "open": round(float(last["open"]), 2),
        "high": round(float(last["high"]), 2),
        "low": round(float(last["low"]), 2),
        "close": round(float(last["close"]), 2),
        "volume": int(last.get("volume", 0)),
        "change_pct": round(change_pct, 2),
    }


async def handle_get_stock_info(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    return {"stock_code": code, "name": code, "market": "sh" if code.startswith("6") else "sz"}


GET_KLINE = ToolDefinition(
    name="get_kline",
    description="获取某只股票的日K线数据（最多120天）。返回每日的开高低收和成交量。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "days": {"type": "integer", "description": "获取最近N个交易日的数据，默认20，最大120", "default": 20},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_kline,
)

GET_STOCK_PRICE = ToolDefinition(
    name="get_stock_price",
    description="快速查看某只股票的最新价格和涨跌幅",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_stock_price,
)

GET_STOCK_INFO = ToolDefinition(
    name="get_stock_info",
    description="查看股票基本信息：名称、所属行业、板块",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_stock_info,
)
