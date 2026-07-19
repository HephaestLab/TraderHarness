"""交易执行工具 — place_order。

薄包装层：做 LLM Agent 特有的前置检查（阶段限制、仓位上限），
然后委托 TradingBus.place_order() 执行。撮合逻辑只在 TradingBus 一处。
"""

from __future__ import annotations

from traderharness.core.market_profile import AShareProfile
from traderharness.tools.registry import ToolContext, ToolDefinition

_PROFILE = AShareProfile()


async def handle_place_order(params: dict, ctx: ToolContext) -> dict:
    # 1. 阶段限制（LLM Agent 特有）
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
    if ctx._bus is None:
        return {"success": False, "error": "无交易总线"}

    # ST 股禁止交易
    valuation_data = ctx.tool_call_cache.get("_valuation_data")
    if valuation_data is not None and not valuation_data.empty:
        st_check = valuation_data[
            (valuation_data["stock_code"] == code) & (valuation_data["date"] < ctx.current_date)
        ]
        if not st_check.empty and st_check.iloc[-1].get("is_st", False):
            return {"success": False, "error": f"{code} 为ST股，禁止交易"}

    # 2. 仓位上限检查（LLM Agent 特有）
    if action == "buy":
        portfolio = ctx.portfolio
        if code not in portfolio.positions and len(portfolio.positions) >= ctx.max_positions:
            return {
                "success": False,
                "error": f"持仓只数已达上限({ctx.max_positions}只)，请先减仓再买入新股",
            }

        window = "open" if ctx.current_phase == "open_window" else "close"
        price = ctx._bus.get_execution_price(code, window)
        if price:
            total_assets = (
                float(portfolio.total_value(ctx.execution_price))
                if ctx.execution_price
                else float(portfolio.cash)
            )
            buy_value = float(price) * _PROFILE.round_lot(quantity)
            existing_value = 0.0
            pos = portfolio.positions.get(code)
            if pos:
                existing_value = float(price) * pos.quantity
            position_after = buy_value + existing_value
            if total_assets > 0 and (position_after / total_assets * 100) > ctx.max_position_pct:
                return {
                    "success": False,
                    "error": (
                        f"买入后{code}仓位占比{position_after / total_assets * 100:.1f}%，"
                        f"超过上限{ctx.max_position_pct:.0f}%"
                    ),
                }

    # 3. 委托 TradingBus 执行（唯一撮合入口）
    window = getattr(ctx, "_current_sub_window", None) or (
        "open" if ctx.current_phase == "open_window" else "close"
    )
    result = ctx._bus.place_order(
        agent_id=ctx.agent_id,
        stock_code=code,
        side=action,
        quantity=quantity,
        stock_name=stock_name,
        reasoning=reasoning,
        window=window,
    )

    if not result.get("success"):
        return result

    # 4. 同步到 ToolContext
    trade = result["trade"]
    ctx.trade_results.append(trade)
    ctx.traded_today.add(code)

    # 5. 构建友好返回
    portfolio_after = {
        "cash": round(float(ctx.portfolio.cash), 2),
        "positions": [{"code": c, "qty": p.quantity} for c, p in ctx.portfolio.positions.items()],
        "position_count": len(ctx.portfolio.positions),
    }

    if action == "buy":
        return {
            "success": True,
            "action": "buy",
            "stock_code": code,
            "price": float(trade["price"]),
            "quantity": trade["quantity"],
            "total_cost": float(trade["total_cost"]),
            "remaining_cash": round(float(ctx.portfolio.cash), 2),
            "portfolio_after": portfolio_after,
        }
    else:
        return {
            "success": True,
            "action": "sell",
            "stock_code": code,
            "price": float(trade["price"]),
            "quantity": trade["quantity"],
            "net_income": float(trade["net_income"]),
            "pnl": round(trade.get("pnl", 0), 2),
            "remaining_cash": round(float(ctx.portfolio.cash), 2),
            "portfolio_after": portfolio_after,
        }


PLACE_ORDER = ToolDefinition(
    name="place_order",
    description="下单买入或卖出股票。只能在开盘窗口和尾盘窗口调用。成交价为当前窗口最后一根5分钟K线的收盘价。",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell"], "description": "买入或卖出"},
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "stock_name": {"type": "string", "description": "股票名称"},
            "quantity": {
                "type": "integer",
                "description": "数量（股），买入必须是100的整数倍。卖出时0表示全部卖出。",
            },
            "reasoning": {"type": "string", "description": "交易理由"},
        },
        "required": ["action", "stock_code", "quantity", "reasoning"],
    },
    handler=handle_place_order,
)
