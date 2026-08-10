"""交易执行工具 — place_order。

薄包装层：做 LLM Agent 特有的前置检查（阶段限制、仓位上限），
然后委托 TradingBus.place_order() 执行。撮合逻辑只在 TradingBus 一处。
"""

from __future__ import annotations

from decimal import Decimal

from traderharness.core.market_profile import AShareProfile
from traderharness.tools.registry import ToolContext, ToolDefinition

_PROFILE = AShareProfile()

_STRUCTURED_BUY_FIELDS = (
    "behavior_hypothesis",
    "confirmation_level",
    "original_structural_stop",
    "exit_condition",
    "expected_holding_days",
)


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

    window = getattr(ctx, "_current_sub_window", None) or (
        "open" if ctx.current_phase == "open_window" else "close"
    )
    execution_price = ctx._bus.get_execution_price(code, window)

    plans = ctx.tool_call_cache.setdefault("_position_plans", {})
    was_new_position = code not in ctx.portfolio.positions

    if action == "buy" and ctx.require_structured_plan and was_new_position:
        missing = [field for field in _STRUCTURED_BUY_FIELDS if params.get(field) in (None, "")]
        if missing:
            return {
                "success": False,
                "error": f"结构化持仓计划缺少字段: {', '.join(missing)}",
            }
        try:
            original_stop = float(params["original_structural_stop"])
            confirmation_level = float(params["confirmation_level"])
            expected_holding_days = int(params["expected_holding_days"])
        except (TypeError, ValueError):
            return {"success": False, "error": "结构化持仓计划的价格和持有期必须是数值"}
        if original_stop <= 0 or confirmation_level <= 0 or expected_holding_days <= 0:
            return {"success": False, "error": "结构化持仓计划的价格和持有期必须大于0"}
        if execution_price is not None and original_stop >= float(execution_price):
            return {
                "success": False,
                "error": "多头仓位的 original_structural_stop 必须低于当前成交价",
            }

    if action == "sell" and ctx.require_structured_plan:
        plan = plans.get(code)
        if plan is None:
            return {"success": False, "error": f"{code} 缺少冻结的结构化持仓计划"}
        holding_days = max(0, ctx.day_index - int(plan["entry_day_index"]))
        minimum_days = int(plan["minimum_holding_days"])
        if holding_days < minimum_days:
            original_stop = float(plan["original_structural_stop"])
            if execution_price is None or float(execution_price) > original_stop:
                return {
                    "success": False,
                    "error": (
                        f"最短持有期未满：已持有{holding_days}个交易日，"
                        f"至少需要{minimum_days}日；当前价尚未触发原始止损{original_stop:.3f}"
                    ),
                    "position_plan": {**plan, "holding_trading_days": holding_days},
                }
            position = ctx.portfolio.positions.get(code)
            if position is not None and quantity not in (0, position.quantity):
                return {
                    "success": False,
                    "error": "最短持有期内触发原始止损时必须一次卖出全部可卖数量",
                    "position_plan": {**plan, "holding_trading_days": holding_days},
                }

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

    if action == "buy" and ctx.require_structured_plan and was_new_position:
        plan = {
            "behavior_hypothesis": str(params["behavior_hypothesis"]),
            "confirmation_level": float(params["confirmation_level"]),
            "original_structural_stop": float(params["original_structural_stop"]),
            "current_protective_stop": float(params["original_structural_stop"]),
            "exit_condition": str(params["exit_condition"]),
            "expected_holding_days": int(params["expected_holding_days"]),
            "minimum_holding_days": ctx.minimum_holding_days,
            "entry_price": float(trade["price"]),
            "entry_date": str(ctx.current_date),
            "entry_day_index": ctx.day_index,
        }
        plans[code] = plan
        # A structured stop is execution state, not prose memory.  Install it
        # automatically so it remains effective even if the model forgets to
        # revisit the position. T+1 means the first useful scan is next day.
        if hasattr(ctx._bus, "create_conditional_order"):
            try:
                conditional = ctx._bus.create_conditional_order(
                    agent_id=ctx.agent_id,
                    stock_code=code,
                    side="sell",
                    quantity=0,
                    comparator="price_lte",
                    trigger_price=Decimal(str(params["original_structural_stop"])),
                    reasoning=f"原始结构止损：{params['exit_condition']}",
                    created_phase=window,
                    protective=True,
                    not_before_day_index=ctx.day_index + 1,
                )
                plan["conditional_order_id"] = conditional["order_id"]
            except (TypeError, ValueError) as exc:
                plan["conditional_order_error"] = str(exc)
    if action == "sell" and code not in ctx.portfolio.positions:
        plans.pop(code, None)

    # 5. 构建友好返回
    portfolio_after = {
        "cash": round(float(ctx.portfolio.cash), 2),
        "positions": [{"code": c, "qty": p.quantity} for c, p in ctx.portfolio.positions.items()],
        "position_count": len(ctx.portfolio.positions),
    }

    if action == "buy":
        response = {
            "success": True,
            "action": "buy",
            "stock_code": code,
            "price": float(trade["price"]),
            "quantity": trade["quantity"],
            "total_cost": float(trade["total_cost"]),
            "remaining_cash": round(float(ctx.portfolio.cash), 2),
            "portfolio_after": portfolio_after,
        }
        plan = plans.get(code)
        if plan and plan.get("conditional_order_id"):
            response["protective_conditional_order_id"] = plan["conditional_order_id"]
        if plan and plan.get("conditional_order_error"):
            response["warning"] = f"成交成功，但自动保护条件单创建失败: {plan['conditional_order_error']}"
        return response
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
            "behavior_hypothesis": {
                "type": "string",
                "description": "新建仓时必填：可证伪的群体行为压力假设",
            },
            "confirmation_level": {
                "type": "number",
                "description": "新建仓时必填：已经确认并需要守住的价格",
            },
            "original_structural_stop": {
                "type": "number",
                "description": "新建仓时必填：冻结的原始结构止损价",
            },
            "exit_condition": {
                "type": "string",
                "description": "新建仓时必填：可机械核验的退出条件",
            },
            "expected_holding_days": {
                "type": "integer",
                "description": "新建仓时必填：预期持有交易日数",
            },
        },
        "required": ["action", "stock_code", "quantity", "reasoning"],
    },
    handler=handle_place_order,
)
