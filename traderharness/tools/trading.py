"""交易执行工具 — place_order。

薄包装层：做 LLM Agent 特有的前置检查（阶段限制、仓位上限），
然后委托 TradingBus.place_order() 执行。撮合逻辑只在 TradingBus 一处。
"""

from __future__ import annotations

import copy
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

_DECISION_CARD_TEXT_FIELDS = (
    "theme",
    "theme_logic",
    "business_fit",
    "sector_confirmation",
    "leadership_comparison",
    "best_expression_reason",
    "capacity_liquidity",
    "price_volume_confirmation",
    "counter_evidence",
    "why_now",
    "abstention_case",
    "invalidation",
)
_DECISION_CARD_FIELDS = frozenset(
    {
        "decision",
        "mode",
        "entry_setup",
        "text_evidence_ids",
        "sector_state",
        "candidate_role",
        "candidate_rank",
        "stronger_candidate_status",
        "execution_compromise",
        "market_stage",
        "extension_assessment",
        "business_fit_basis",
        *_DECISION_CARD_TEXT_FIELDS,
    }
)


def _order_error(
    message: str,
    *,
    error_code: str,
    retryable: bool,
    correction: dict | None = None,
) -> dict:
    payload = {
        "success": False,
        "error": message,
        "error_code": error_code,
        "retryable": retryable,
    }
    if retryable:
        payload["retry_kind"] = "decision_card_correction"
    payload["correction"] = {
        "scope": "format_and_evidence_only",
        "semantic_fields_must_not_change": [
            "decision",
            "mode",
            "entry_setup",
            "sector_state",
            "candidate_role",
            "candidate_rank",
            "stronger_candidate_status",
            "execution_compromise",
            "extension_assessment",
        ],
        **(correction or {}),
    }
    return payload


def _retryable_card_error(message: str, error_code: str, **correction) -> dict:
    return _order_error(
        message,
        error_code=error_code,
        retryable=True,
        correction={
            "instruction": (
                "只修正字段层级、遗漏字段、类型或证据ID；不得为了通过校验改变原有语义结论。"
            ),
            **correction,
        },
    )


def _semantic_card_rejection(message: str) -> dict:
    return _order_error(
        message,
        error_code="decision_card_semantic_rejection",
        retryable=False,
        correction={
            "instruction": "保持原语义结论，本阶段不得自动改写为可交易；应等待新证据。"
        },
    )


def _validate_decision_card(value) -> dict | None:
    """Validate the LLM's own semantic verdict, never calculate it for the model."""
    if not isinstance(value, dict):
        return _retryable_card_error(
            "decision_card 必须是结构化对象",
            "decision_card_invalid_type",
            expected_type="object",
        )

    unexpected = sorted(set(value) - _DECISION_CARD_FIELDS)
    if unexpected:
        return _retryable_card_error(
            "decision_card 包含不属于裁决卡的字段: " + ", ".join(unexpected),
            "decision_card_unknown_fields",
            invalid_fields=unexpected,
            allowed_decision_card_fields=sorted(_DECISION_CARD_FIELDS),
            place_at_order_top_level=[
                field for field in unexpected if field in _STRUCTURED_BUY_FIELDS
            ],
        )

    missing = [field for field in _DECISION_CARD_TEXT_FIELDS if not str(value.get(field, "")).strip()]
    for field in (
        "decision",
        "mode",
        "entry_setup",
        "candidate_role",
        "candidate_rank",
        "stronger_candidate_status",
        "execution_compromise",
        "sector_state",
        "market_stage",
        "extension_assessment",
        "business_fit_basis",
    ):
        if not str(value.get(field, "")).strip():
            missing.append(field)
    evidence_ids = value.get("text_evidence_ids")
    if not isinstance(evidence_ids, list) or not any(str(item).strip() for item in evidence_ids):
        missing.append("text_evidence_ids")
    if missing:
        missing = sorted(set(missing))
        return _retryable_card_error(
            "decision_card 缺少字段: " + ", ".join(missing),
            "decision_card_missing_fields",
            missing_fields=missing,
            allowed_decision_card_fields=sorted(_DECISION_CARD_FIELDS),
        )

    decision = str(value["decision"])
    if decision != "trade":
        return _semantic_card_rejection(
            f"decision_card 的 decision={decision}；abstain 结论不能下单"
        )

    mode = str(value["mode"])
    role = str(value["candidate_role"])
    expected_roles = {
        "leader_attack": {"emerging_leader", "true_leader"},
        "high_low_rotation": {"rotation_core"},
    }
    allowed_roles = expected_roles.get(mode)
    if allowed_roles is None:
        return _semantic_card_rejection(f"decision_card mode 无效: {mode}")
    if role not in allowed_roles:
        return _semantic_card_rejection(
            f"decision_card candidate_role={role} 与 mode={mode} 不一致；"
            f"只有 {', '.join(sorted(allowed_roles))} 可以执行该模式"
        )

    entry_setup = str(value["entry_setup"])
    valid_setups = {
        "leader_attack": {
            "low_base_ignition",
            "trend_continuation",
            "leader_pullback",
        },
        "high_low_rotation": {"low_base_ignition", "trend_continuation"},
    }
    if entry_setup not in valid_setups[mode]:
        return _semantic_card_rejection(
            f"decision_card entry_setup={entry_setup} 与 mode={mode} 不一致；"
            f"允许值为 {', '.join(sorted(valid_setups[mode]))}"
        )

    sector_state = str(value["sector_state"])
    allowed_sector_states = {
        ("leader_attack", "low_base_ignition"): {
            "emerging_leading",
            "confirmed_leading",
        },
        ("leader_attack", "trend_continuation"): {"confirmed_leading"},
        ("leader_attack", "leader_pullback"): {"confirmed_leading"},
        ("high_low_rotation", "low_base_ignition"): {
            "emerging_repricing",
            "confirmed_repricing",
        },
        ("high_low_rotation", "trend_continuation"): {"confirmed_repricing"},
    }
    expected_sector_states = allowed_sector_states[(mode, entry_setup)]
    if sector_state not in expected_sector_states:
        return _semantic_card_rejection(
            f"decision_card sector_state={sector_state} 与 mode={mode}/"
            f"{entry_setup} 不一致；允许值为 {', '.join(sorted(expected_sector_states))}，"
            "single_stock_only 或 unclear 应放弃"
        )

    extension = str(value["extension_assessment"])
    if extension not in {"acceptable", "managed_extension"}:
        return _semantic_card_rejection(
            f"decision_card extension_assessment={extension}；"
            "overextended 或 unclear 时应等待而不是降级购买跟随者"
        )
    candidate_rank = str(value["candidate_rank"])
    if candidate_rank != "best_expression":
        return _semantic_card_rejection(
            f"decision_card candidate_rank={candidate_rank}；"
            "较弱备选或地位不清的候选不能下单"
        )
    stronger_status = str(value["stronger_candidate_status"])
    if stronger_status != "none_identified":
        return _semantic_card_rejection(
            f"decision_card stronger_candidate_status={stronger_status}；"
            "存在更强候选时，不得因其不可成交而降级购买次强股票"
        )
    compromise = str(value["execution_compromise"])
    if compromise != "none":
        return _semantic_card_rejection(
            f"decision_card execution_compromise={compromise}；"
            "执行便利不能替代语义上的最优表达"
        )
    if value["business_fit_basis"] not in {
        "direct_segments",
        "industry_proxy",
        "announcement",
    }:
        return _retryable_card_error(
            "decision_card business_fit_basis 无效",
            "decision_card_invalid_business_fit_basis",
            allowed_values=["direct_segments", "industry_proxy", "announcement"],
        )
    return None


def _validate_grounded_candidate_evidence(
    code: str, decision_card: dict, ctx: ToolContext
) -> tuple[dict | None, dict]:
    evidence = ctx.tool_call_cache.get("_agent_tool_results", {})
    required = (
        "get_stock_info",
        "get_business_segments",
        "get_valuation",
        "get_kline",
        "get_stock_price",
    )
    missing = [name for name in required if code not in evidence.get(name, {})]
    if missing:
        return (
            _retryable_card_error(
                "下单前缺少该候选的成功工具证据: " + ", ".join(missing),
                "decision_card_missing_tool_evidence",
                stock_code=code,
                missing_tools=missing,
                instruction=(
                    "保持原语义结论；先用缺失工具核验同一候选，"
                    "只有成功返回后才能重新提交下单。"
                ),
            ),
            {},
        )

    basis = decision_card["business_fit_basis"]
    segments_result = evidence["get_business_segments"][code]
    if basis == "direct_segments":
        segments = segments_result.get("segments") or []
        named_segments = [
            item for item in segments if str(item.get("name", "")).strip()
        ]
        if not named_segments:
            return (
                _retryable_card_error(
                    "business_fit_basis=direct_segments，但工具没有返回可用主营分部名称",
                    "decision_card_ungrounded_business_fit",
                    instruction=(
                        "不得虚构产品或主营；若只能依靠行业分类，请保持其他语义不变，"
                        "将 business_fit_basis 改为 industry_proxy 并明确证据局限。"
                    ),
                ),
                {},
            )
    if basis == "announcement" and code not in evidence.get(
        "get_announcement_evidence", {}
    ):
        return (
            _retryable_card_error(
                "business_fit_basis=announcement，但未成功查询该候选的公告证据",
                "decision_card_missing_announcement_evidence",
                missing_tools=["get_announcement_evidence"],
            ),
            {},
        )

    snapshot = {
        name: copy.deepcopy(evidence[name][code])
        for name in required
    }
    if code in evidence.get("get_announcement_evidence", {}):
        snapshot["get_announcement_evidence"] = copy.deepcopy(
            evidence["get_announcement_evidence"][code]
        )
    return None, snapshot


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
            return _order_error(
                f"结构化持仓计划缺少字段: {', '.join(missing)}",
                error_code="structured_plan_missing_fields",
                retryable=True,
                correction={
                    "instruction": (
                        "把缺失字段放在 place_order 顶层，不要放入 decision_card；"
                        "只修正结构，不得改变原语义结论。"
                    ),
                    "place_at_order_top_level": missing,
                    "decision_card_must_not_contain": list(_STRUCTURED_BUY_FIELDS),
                },
            )
        try:
            original_stop = float(params["original_structural_stop"])
            confirmation_level = float(params["confirmation_level"])
            expected_holding_days = int(params["expected_holding_days"])
        except (TypeError, ValueError):
            return _order_error(
                "结构化持仓计划的价格和持有期必须是数值",
                error_code="structured_plan_invalid_types",
                retryable=True,
                correction={
                    "instruction": "只修正顶层字段类型，不得改变原语义结论。",
                    "numeric_fields": [
                        "confirmation_level",
                        "original_structural_stop",
                        "expected_holding_days",
                    ],
                },
            )
        if original_stop <= 0 or confirmation_level <= 0 or expected_holding_days <= 0:
            return {"success": False, "error": "结构化持仓计划的价格和持有期必须大于0"}
        if execution_price is not None and original_stop >= float(execution_price):
            return {
                "success": False,
                "error": "多头仓位的 original_structural_stop 必须低于当前成交价",
            }

    if action == "buy" and ctx.require_decision_card and was_new_position:
        decision_error = _validate_decision_card(params.get("decision_card"))
        if decision_error:
            return decision_error
        visible_evidence_ids = ctx.tool_call_cache.get("_visible_text_evidence_ids")
        if visible_evidence_ids is not None:
            submitted_ids = {
                str(item) for item in params["decision_card"]["text_evidence_ids"]
            }
            unknown_ids = sorted(submitted_ids - set(visible_evidence_ids))
            if unknown_ids:
                return _retryable_card_error(
                    "decision_card 引用了未由工具返回的文本证据ID: "
                    + ", ".join(unknown_ids),
                    "decision_card_unseen_evidence",
                    invalid_evidence_ids=unknown_ids,
                    available_evidence_ids=sorted(set(visible_evidence_ids))[:60],
                )
        evidence_error, evidence_snapshot = _validate_grounded_candidate_evidence(
            code, params["decision_card"], ctx
        )
        if evidence_error:
            return evidence_error
        if execution_price is not None and float(execution_price) < confirmation_level:
            return _semantic_card_rejection(
                "当前成交价尚未达到 confirmation_level；确认条件未触发，不得提前入场"
            )

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
        if ctx.require_decision_card:
            plan["decision_card"] = copy.deepcopy(params["decision_card"])
            plan["decision_evidence_snapshot"] = evidence_snapshot
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
            "decision_card": {
                "type": "object",
                "additionalProperties": False,
                "description": (
                    "要求语义决策卡的 Agent 新建仓时必填。Python只提供事实；"
                    "主题逻辑、主营契合、龙头地位、容量、阶段与反证由你综合裁决。"
                ),
                "properties": {
                    "decision": {"type": "string", "enum": ["trade", "abstain"]},
                    "mode": {
                        "type": "string",
                        "enum": ["leader_attack", "high_low_rotation"],
                    },
                    "entry_setup": {
                        "type": "string",
                        "enum": [
                            "low_base_ignition",
                            "trend_continuation",
                            "leader_pullback",
                        ],
                        "description": (
                            "明确本次是低位启动、趋势持续启动还是龙头回踩；"
                            "回踩不是 leader_attack 的唯一入口。"
                        ),
                    },
                    "theme": {"type": "string"},
                    "theme_logic": {"type": "string"},
                    "text_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "business_fit": {"type": "string"},
                    "business_fit_basis": {
                        "type": "string",
                        "enum": ["direct_segments", "industry_proxy", "announcement"],
                        "description": (
                            "主营契合结论的证据类型。direct_segments 只能在主营工具返回"
                            "明确分部名称时使用；industry_proxy 必须承认仅有行业代理证据。"
                        ),
                    },
                    "sector_state": {
                        "type": "string",
                        "enum": [
                            "emerging_leading",
                            "confirmed_leading",
                            "emerging_repricing",
                            "confirmed_repricing",
                            "single_stock_only",
                            "unclear",
                        ],
                    },
                    "sector_confirmation": {"type": "string"},
                    "candidate_role": {
                        "type": "string",
                        "enum": [
                            "emerging_leader",
                            "true_leader",
                            "rotation_core",
                            "follower",
                            "unclear",
                        ],
                    },
                    "leadership_comparison": {"type": "string"},
                    "best_expression_reason": {
                        "type": "string",
                        "description": (
                            "解释为什么当前股票是该主题与模式的最优可交易表达；"
                            "成交方便不能作为把次强候选改称最优表达的理由。"
                        ),
                    },
                    "candidate_rank": {
                        "type": "string",
                        "enum": ["best_expression", "weaker_alternative", "unclear"],
                    },
                    "stronger_candidate_status": {
                        "type": "string",
                        "enum": ["none_identified", "available", "unavailable"],
                        "description": (
                            "若比较中存在更强候选，无论是否涨停或难买，都不得填写 "
                            "none_identified。"
                        ),
                    },
                    "execution_compromise": {
                        "type": "string",
                        "enum": ["none", "weaker_substitute", "unclear"],
                        "description": "是否因为更容易成交而降级选择了较弱候选。",
                    },
                    "capacity_liquidity": {"type": "string"},
                    "price_volume_confirmation": {"type": "string"},
                    "market_stage": {
                        "type": "string",
                        "enum": [
                            "startup",
                            "confirmation",
                            "healthy_pullback",
                            "acceleration",
                            "climax",
                            "distribution",
                            "repricing",
                        ],
                    },
                    "extension_assessment": {
                        "type": "string",
                        "enum": [
                            "acceptable",
                            "managed_extension",
                            "overextended",
                            "unclear",
                        ],
                    },
                    "counter_evidence": {"type": "string"},
                    "why_now": {"type": "string"},
                    "abstention_case": {"type": "string"},
                    "invalidation": {"type": "string"},
                },
                "required": [
                    "decision",
                    "mode",
                    "entry_setup",
                    "theme",
                    "theme_logic",
                    "text_evidence_ids",
                    "business_fit",
                    "business_fit_basis",
                    "sector_state",
                    "sector_confirmation",
                    "candidate_role",
                    "leadership_comparison",
                    "best_expression_reason",
                    "candidate_rank",
                    "stronger_candidate_status",
                    "execution_compromise",
                    "capacity_liquidity",
                    "price_volume_confirmation",
                    "market_stage",
                    "extension_assessment",
                    "counter_evidence",
                    "why_now",
                    "abstention_case",
                    "invalidation",
                ],
            },
        },
        "required": ["action", "stock_code", "quantity", "reasoning"],
    },
    handler=handle_place_order,
)
