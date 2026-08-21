"""Manage environment-owned, price-triggered orders."""

from __future__ import annotations

from decimal import Decimal

from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition


def _phase(ctx: ToolContext) -> str:
    return getattr(ctx, "_current_sub_window", None) or ctx.current_phase


def _visible_order(order: dict, ctx: ToolContext) -> dict:
    """Expose relative expiry in v5 so internal day indexes are not copied as input."""
    visible = dict(order)
    if not is_current_contract(getattr(ctx, "tool_contract_version", None)):
        return visible
    expiry = visible.pop("expires_day_index", None)
    visible["expires_in_trading_days"] = max(0, int(expiry) - int(ctx.day_index)) if expiry is not None else None
    return visible


def _visible_result(result: dict, ctx: ToolContext) -> dict:
    visible = dict(result)
    if isinstance(visible.get("order"), dict):
        visible["order"] = _visible_order(visible["order"], ctx)
    return visible


async def handle_manage_conditional_order(params: dict, ctx: ToolContext) -> dict:
    if ctx._bus is None:
        return {"success": False, "error": "无交易总线"}
    operation = params.get("operation", "")
    try:
        if operation == "create":
            side = params.get("action", "")
            code = params.get("stock_code", "")
            comparator = params.get("comparator", "")
            trigger_price = params.get("trigger_price")
            if not code or trigger_price is None:
                return {"success": False, "error": "创建条件单需要 stock_code 和 trigger_price"}
            if side == "buy" and ctx.require_structured_plan:
                return {
                    "success": False,
                    "error": "结构化计划 Agent 必须先用 place_order 建仓并冻结计划，不能用条件单绕过",
                }
            protective = bool(params.get("protective", False))
            not_before = ctx.day_index
            plans = ctx.tool_call_cache.get("_position_plans", {})
            plan = plans.get(code)
            if side == "sell" and plan is not None:
                original = Decimal(str(plan["original_structural_stop"]))
                trigger = Decimal(str(trigger_price))
                is_original_hard_stop = comparator == "price_lte" and trigger <= original
                protective = protective or is_original_hard_stop
                if not is_original_hard_stop:
                    not_before = int(plan["entry_day_index"]) + int(plan["minimum_holding_days"])
            expires_day_index = params.get("expires_day_index")
            if params.get("expires_in_trading_days") is not None:
                expires_day_index = ctx.day_index + int(params["expires_in_trading_days"])
            order = ctx._bus.create_conditional_order(
                agent_id=ctx.agent_id,
                stock_code=code,
                side=side,
                quantity=params.get("quantity", 0),
                comparator=comparator,
                trigger_price=Decimal(str(trigger_price)),
                reasoning=params.get("reasoning", ""),
                created_phase=_phase(ctx),
                protective=protective,
                expires_day_index=expires_day_index,
                not_before_day_index=not_before,
                max_positions=ctx.max_positions,
                max_position_pct=ctx.max_position_pct,
            )
            return {"success": True, "order": _visible_order(order, ctx)}
        if operation == "update":
            order_id = params.get("order_id", "")
            current = next(
                (order for order in ctx._bus.list_conditional_orders(status=None) if order["order_id"] == order_id),
                None,
            )
            not_before = None
            if current is not None and current.get("protective") and params.get("trigger_price") is not None:
                plan = ctx.tool_call_cache.get("_position_plans", {}).get(current["stock_code"])
                if plan is not None and Decimal(str(params["trigger_price"])) > Decimal(
                    str(plan["original_structural_stop"])
                ):
                    not_before = int(plan["entry_day_index"]) + int(plan["minimum_holding_days"])
            result = ctx._bus.update_conditional_order(
                order_id,
                trigger_price=(
                    Decimal(str(params["trigger_price"])) if params.get("trigger_price") is not None else None
                ),
                quantity=params.get("quantity"),
                reasoning=params.get("reasoning", ""),
                created_phase=_phase(ctx),
                not_before_day_index=not_before,
            )
            if result.get("success") and current is not None:
                plan = ctx.tool_call_cache.get("_position_plans", {}).get(current["stock_code"])
                if plan is not None and params.get("trigger_price") is not None:
                    plan["current_protective_stop"] = float(params["trigger_price"])
            return _visible_result(result, ctx)
        if operation == "cancel":
            return _visible_result(
                ctx._bus.cancel_conditional_order(
                    params.get("order_id", ""),
                    reasoning=params.get("reasoning", ""),
                ),
                ctx,
            )
        return {"success": False, "error": "operation 必须是 create、update 或 cancel"}
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc)}


async def handle_list_conditional_orders(params: dict, ctx: ToolContext) -> dict:
    if ctx._bus is None:
        return {"error": "无交易总线"}
    status = params.get("status", "active")
    orders = [_visible_order(order, ctx) for order in ctx._bus.list_conditional_orders(status=status)]
    result = {"orders": orders}
    if is_current_contract(getattr(ctx, "tool_contract_version", None)):
        result.update({"count": len(orders), "status_filter": status})
    return result


MANAGE_CONDITIONAL_ORDER = ToolDefinition(
    name="manage_conditional_order",
    description=(
        "创建、修改或取消条件单。环境逐根检查后续5分钟bar收盘价，首次满足条件时自动通过"
        "TradingBus.place_order成交；已揭示的bar不会被追溯触发。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["create", "update", "cancel"]},
            "order_id": {"type": "string"},
            "action": {"type": "string", "enum": ["buy", "sell"]},
            "stock_code": {"type": "string"},
            "quantity": {"type": "integer", "description": "卖出时0表示触发时全部可卖"},
            "comparator": {"type": "string", "enum": ["price_lte", "price_gte"]},
            "trigger_price": {"type": "number"},
            "protective": {"type": "boolean", "description": "保护止损只能上移"},
            "expires_day_index": {"type": "integer"},
            "reasoning": {"type": "string"},
        },
        "required": ["operation", "reasoning"],
    },
    handler=handle_manage_conditional_order,
)

LIST_CONDITIONAL_ORDERS = ToolDefinition(
    name="list_conditional_orders",
    description="查看活动、已触发、已取消或全部条件单及其版本和失败尝试。",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["active", "triggered", "cancelled", "expired", "all"],
            }
        },
    },
    handler=handle_list_conditional_orders,
)
