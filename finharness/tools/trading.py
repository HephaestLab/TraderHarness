"""交易执行工具 — place_order。

直接从源项目 backend/agents/agentic/tools/trading_tools.py 迁移。
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from finharness.tools.registry import ToolDefinition, ToolContext
from finharness.core.market_profile import AShareProfile

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")
_PROFILE = AShareProfile()


async def handle_place_order(params: dict, ctx: ToolContext) -> dict:
    if ctx.current_phase == "pre_market":
        return {"success": False, "error": "盘前分析阶段不能下单，请在开盘窗口或尾盘窗口下单"}

    action = params.get("action", "").lower()
    code = params.get("stock_code", "")
    stock_name = params.get("stock_name", code)
    quantity = params.get("quantity", 0)
    reasoning = params.get("reasoning", "")

    if action not in ("buy", "sell"):
        return {"success": False, "error": f"无效操作: {action}，必须是 buy 或 sell"}
    if not code:
        return {"success": False, "error": "stock_code 不能为空"}

    if code in ctx.traded_today:
        return {"success": False, "error": f"{code} 今天已交易过，禁止同日重复操作"}

    price = ctx.execution_price.get(code)
    if price is None and ctx._bus is not None:
        window = "open" if ctx.current_phase == "open_window" else "close"
        price = ctx._bus.get_execution_price(code, window)
    if price is None:
        return {"success": False, "error": f"{code} 无法获取成交价（当天可能无交易数据）"}

    if action == "buy":
        if code not in ctx.portfolio.positions:
            if len(ctx.portfolio.positions) >= ctx.max_positions:
                return {"success": False, "error": f"持仓只数已达上限({ctx.max_positions}只)，请先减仓再买入新股"}

        total_assets = float(ctx.portfolio.total_value(ctx.execution_price)) if ctx.execution_price else float(ctx.portfolio.cash)
        buy_value = float(price) * _PROFILE.round_lot(quantity)
        existing_value = 0.0
        pos = ctx.portfolio.positions.get(code)
        if pos and price:
            existing_value = float(price) * pos.quantity
        position_after = buy_value + existing_value
        if total_assets > 0 and (position_after / total_assets * 100) > ctx.max_position_pct:
            return {"success": False, "error": f"买入后{code}仓位占比{position_after/total_assets*100:.1f}%，超过上限{ctx.max_position_pct:.0f}%"}

    prev_date_data = ctx.preloaded_daily.get(code)
    if prev_date_data is not None and not prev_date_data.empty:
        filtered = prev_date_data[prev_date_data["date"] < ctx.current_date]
        if not filtered.empty:
            prev_close = Decimal(str(filtered.iloc[-1]["close"])).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            limit_up, limit_down = _PROFILE.price_limits(code, prev_close)
            if price >= limit_up:
                return {"success": False, "error": f"{code} 涨停 (涨停价 {limit_up})"}
            if price <= limit_down:
                return {"success": False, "error": f"{code} 跌停 (跌停价 {limit_down})"}

    try:
        if action == "buy":
            qty = _PROFILE.round_lot(quantity)
            if qty <= 0:
                return {"success": False, "error": f"买入数量 {quantity} 不足1手（100股）"}
            trade = ctx.portfolio.buy(code, stock_name, price, qty, ctx.current_date)
        else:
            pos = ctx.portfolio.positions.get(code)
            if pos is None:
                return {"success": False, "error": f"未持有 {code}，无法卖出"}
            sellable = pos.sellable_quantity(ctx.current_date)
            qty = min(quantity, sellable) if quantity > 0 else sellable
            if qty <= 0:
                return {"success": False, "error": f"{code} T+1限制，今日无可卖数量"}
            trade = ctx.portfolio.sell(code, price, qty, ctx.current_date)
            if pos.avg_cost:
                trade["pnl"] = float(trade["net_income"]) - float(pos.avg_cost * qty)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    trade["signal_reasoning"] = reasoning
    trade["date"] = str(ctx.current_date)
    ctx.trade_results.append(trade)
    ctx.traded_today.add(code)
    # Also record to bus.trade_history so EngineResult collects it
    if ctx._bus is not None:
        ctx._bus.trade_history.append(trade)

    portfolio_after = {
        "cash": round(float(ctx.portfolio.cash), 2),
        "positions": [{"code": c, "qty": p.quantity} for c, p in ctx.portfolio.positions.items()],
        "position_count": len(ctx.portfolio.positions),
    }

    if action == "buy":
        return {
            "success": True, "action": "buy", "stock_code": code,
            "price": float(price), "quantity": trade["quantity"],
            "total_cost": float(trade["total_cost"]),
            "remaining_cash": round(float(ctx.portfolio.cash), 2),
            "portfolio_after": portfolio_after,
        }
    else:
        return {
            "success": True, "action": "sell", "stock_code": code,
            "price": float(price), "quantity": trade["quantity"],
            "net_income": float(trade["net_income"]),
            "pnl": round(trade.get("pnl", 0), 2),
            "remaining_cash": round(float(ctx.portfolio.cash), 2),
            "portfolio_after": portfolio_after,
        }


PLACE_ORDER = ToolDefinition(
    name="place_order",
    description="下单买入或卖出股票。只能在开盘窗口和尾盘窗口调用。",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell"], "description": "买入或卖出"},
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "stock_name": {"type": "string", "description": "股票名称"},
            "quantity": {"type": "integer", "description": "数量（股），买入必须是100的整数倍。卖出时0表示全部卖出。"},
            "reasoning": {"type": "string", "description": "交易理由"},
        },
        "required": ["action", "stock_code", "quantity", "reasoning"],
    },
    handler=handle_place_order,
)
