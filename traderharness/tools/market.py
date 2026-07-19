"""市场数据工具 — get_kline, get_stock_price, get_stock_info。

直接从源项目 backend/agents/agentic/tools/market_tools.py 迁移。
"""

from __future__ import annotations

import logging

import pandas as pd

from traderharness.tools.dedup import with_dedup
from traderharness.tools.registry import ToolContext, ToolDefinition

logger = logging.getLogger(__name__)


async def _ensure_daily_data(code: str, ctx: ToolContext) -> pd.DataFrame | None:
    """获取日K数据。全量数据已在回测启动时加载到 preloaded_daily。"""
    if code in ctx.preloaded_daily:
        df = ctx.preloaded_daily[code]
        if df is not None and not df.empty:
            return df

    # Fallback: 从 bus.market 直接取（bus.market 也是同一份内存数据）
    if ctx._bus is not None:
        df = ctx._bus.market.get(code)
        if not df.empty:
            ctx.preloaded_daily[code] = df
            return df

    return None


async def handle_get_kline(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    days = min(params.get("days", 20), 120)

    df = await _ensure_daily_data(code, ctx)
    if df is None or df.empty:
        return {"error": f"无法获取 {code} 的行情数据"}

    filtered = df[df["date"] < ctx.current_date].tail(days)
    if filtered.empty:
        return {"error": f"{code} 在当前交易日之前无数据"}

    # Recent 20 days: return full OHLCV with relative day labels.
    # Masked: calendar offset "D-N"; unmasked fallback: trading-day "T-N".
    masker = getattr(ctx, "date_masker", None)
    recent = filtered.tail(20)
    records = []
    n = len(recent)
    for i, (_, row) in enumerate(recent.iterrows()):
        offset = n - i
        day_label = masker.mask_date(row["date"]) if masker is not None else f"T-{offset}"
        records.append(
            {
                "day": day_label,
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row.get("volume", 0)),
            }
        )

    result = {"stock_code": code, "count": len(filtered), "recent_20": records}

    # If requested more than 20 days, add summary of older period
    if len(filtered) > 20:
        older = filtered.iloc[:-20]
        closes = older["close"].astype(float)
        volumes = older["volume"].astype(float)
        result["older_summary"] = {
            "period_days": len(older),
            "high": round(float(older["high"].max()), 2),
            "low": round(float(older["low"].min()), 2),
            "open_price": round(float(older.iloc[0]["open"]), 2),
            "close_price": round(float(older.iloc[-1]["close"]), 2),
            "change_pct": round(
                (float(older.iloc[-1]["close"]) - float(older.iloc[0]["open"]))
                / float(older.iloc[0]["open"])
                * 100,
                2,
            ),
            "avg_volume": int(volumes.mean()),
            "ma5_end": round(float(closes.tail(5).mean()), 2),
            "ma10_end": round(float(closes.tail(10).mean()), 2),
            "ma20_end": round(float(closes.tail(20).mean()), 2) if len(closes) >= 20 else None,
        }

    return result


async def handle_get_stock_price(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")

    df = await _ensure_daily_data(code, ctx)
    if df is None or df.empty:
        return {"error": f"无法获取 {code} 的行情数据"}

    filtered = df[df["date"] < ctx.current_date]
    if filtered.empty:
        return {"error": f"{code} 在当前交易日之前无数据"}

    last = filtered.iloc[-1]
    prev = filtered.iloc[-2] if len(filtered) >= 2 else last
    prev_close = float(prev["close"])
    change_pct = (
        ((float(last["close"]) - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
    )

    masker = getattr(ctx, "date_masker", None)
    day_label = masker.mask_date(last["date"]) if masker is not None else "T-1"

    return {
        "stock_code": code,
        "day": day_label,
        "open": round(float(last["open"]), 2),
        "high": round(float(last["high"]), 2),
        "low": round(float(last["low"]), 2),
        "close": round(float(last["close"]), 2),
        "volume": int(last.get("volume", 0)),
        "change_pct": round(change_pct, 2),
    }


async def handle_get_stock_info(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    if not code:
        return {"error": "stock_code 不能为空"}

    # Only serve codes inside this run's market universe. The full packaged
    # registry covers stocks the run has no data for; answering those would
    # emit a real company name the entity masker has no alias mapping for.
    df = await _ensure_daily_data(code, ctx)
    if df is None or df.empty:
        return {"error": f"{code} 不在本次回测数据范围内，无法查询"}

    from traderharness.data.stock_registry_loader import get_stock_info as _get_info

    info = _get_info(code)
    return {
        "stock_code": code,
        "name": info.get("name", code),
        "industry": info.get("industry", "未知"),
        "market": info.get("market", "主板"),
    }


GET_KLINE = ToolDefinition(
    name="get_kline",
    description="获取日K线。最近20天返回逐日OHLCV；超过20天的部分返回统计摘要（区间高低、涨跌幅、均线）。如需全量原始数据请用execute_code。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "days": {
                "type": "integer",
                "description": "获取最近N个交易日的数据，默认20，最大120",
                "default": 20,
            },
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
    handler=with_dedup(handle_get_stock_info),
)
