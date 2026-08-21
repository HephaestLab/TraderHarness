"""Tool 注册中心 — 管理所有 tool 的 schema 定义和执行分发。

直接从源项目 backend/agents/agentic/tool_registry.py 迁移。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from traderharness.core.portfolio import Portfolio
from traderharness.tools.contracts import (
    NON_RETRYABLE_ERROR_CODES,
    build_current_description,
    build_current_parameters,
    is_current_contract,
    output_schema_for,
    tool_example,
    validate_instance,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """每日工具执行上下文 — 所有 tool handler 共享此对象。"""

    current_date: date
    current_phase: str  # "pre_market" | "open_window" | "close_window"
    portfolio: Portfolio
    initial_cash: Decimal
    preloaded_daily: dict[str, pd.DataFrame] = field(default_factory=dict)
    preloaded_5min: dict[str, pd.DataFrame] = field(default_factory=dict)
    window_minutes: dict[str, pd.DataFrame] = field(default_factory=dict)
    execution_price: dict[str, Decimal] = field(default_factory=dict)
    close_prices: dict[str, Decimal] = field(default_factory=dict)
    trade_results: list[dict] = field(default_factory=list)
    traded_today: set[str] = field(default_factory=set)
    tool_call_cache: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    workspace_root: str = ""
    max_position_pct: float = 25.0
    max_positions: int = 4
    require_structured_plan: bool = False
    require_decision_card: bool = False
    require_phase_completion: bool = False
    minimum_holding_days: int = 0
    day_index: int = 0
    research_interval_days: int = 0
    full_market_research_allowed: bool | None = None
    sandbox_pre_market_only: bool = False
    allowed_tools: frozenset[str] | None = None
    sandbox_max_calls_per_day: int = 0
    watchlist_ttl_days: int = 0
    max_active_memories: int = 0
    max_daily_memories: int = 0
    date_masker: Any = None
    entity_masker: Any = None
    replay_mode: bool = False
    tool_contract_version: str = "v4"
    _bus: Any = field(default=None, repr=False)
    _workspace: Any = field(default=None, repr=False)


@dataclass
class ToolDefinition:
    """单个 tool 的定义。"""

    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], Awaitable[dict]]
    # Most handlers return canonical engine values and rely on the registry to
    # mask their egress. A trusted boundary such as execute_code is different:
    # every object exposed inside its sandbox is already masked before Agent
    # code can inspect it, so applying the permutation again would change the
    # pseudocode and make subsequent tool calls address the wrong security.
    handler_masks_egress: bool = False

    def to_openai_schema(
        self,
        *,
        contract_version: str | None = None,
        ctx: ToolContext | None = None,
    ) -> dict:
        description = self.description
        parameters = self.parameters
        if is_current_contract(contract_version):
            description = build_current_description(self.name, description)
            parameters = build_current_parameters(self.name, parameters, ctx)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description,
                "parameters": parameters,
            },
        }

    def output_schema(self, *, contract_version: str | None = None) -> dict | None:
        """Return the documented result contract for audit/UI consumers."""
        if not is_current_contract(contract_version):
            return None
        return output_schema_for(self.name)


class ToolRegistry:
    """Tool 注册和分发中心。"""

    def __init__(self, *, contract_version: str = "v4") -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.contract_version = contract_version

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_openai_tools_schema(
        self,
        *,
        exclude: set[str] | None = None,
        ctx: ToolContext | None = None,
    ) -> list[dict]:
        exclude = exclude or set()
        return [
            t.to_openai_schema(contract_version=self.contract_version, ctx=ctx)
            for t in self._tools.values()
            if t.name not in exclude
        ]

    def get_contract_catalog(self, *, ctx: ToolContext | None = None) -> list[dict]:
        """Return input/output/examples together for docs, UI, and contract tests."""
        return [
            {
                "name": tool.name,
                "input": tool.to_openai_schema(
                    contract_version=self.contract_version,
                    ctx=ctx,
                )["function"]["parameters"],
                "output": tool.output_schema(contract_version=self.contract_version),
                "example": tool_example(tool.name),
            }
            for tool in self._tools.values()
        ]

    @staticmethod
    def _error_payload(
        tool_name: str,
        arguments: dict,
        raw: dict,
        *,
        default_code: str = "tool_rejected",
    ) -> dict:
        message = str(raw.get("error") or "工具拒绝了本次调用")
        inferred_code = default_code
        inferred_retryable = True
        inferred_instruction = "根据 error_code 修正参数后在当前阶段重试。"
        inferred_details: dict[str, Any] = {}
        if any(
            token in message
            for token in (
                "未加载",
                "当前交易日无市场数据",
                "无基本面数据",
                "无估值数据",
                "无主营业务数据",
            )
        ):
            inferred_code = "data_unavailable"
            inferred_retryable = False
            inferred_instruction = "当前回测数据不包含该信息；使用其他已成功返回的证据继续。"
        elif any(
            token in message
            for token in (
                "不在本次回测数据范围",
                "当前交易日之前无",
                "无法获取",
            )
        ):
            inferred_code = "security_data_unavailable"
            inferred_retryable = False
            inferred_instruction = "不要重复查询该证券；换用当前可见股票池中的完整代码。"
        elif "未找到板块" in message:
            inferred_code = "sector_not_found"
            inferred_instruction = "先调用 get_market_overview，复制其中的完整可见板块名称后重试。"
            inferred_details["required_tool"] = "get_market_overview"
        elif "记忆不存在" in message:
            inferred_code = "memory_not_found"
            inferred_instruction = "调用 search_memory 获取当前可见的准确 memory_id 后重试；不要猜测 ID。"
            inferred_details["required_tool"] = "search_memory"
        elif "未持有" in message:
            inferred_code = "position_not_held"
            inferred_retryable = False
            inferred_instruction = "先调用 get_portfolio 确认当前持仓，不要重复卖出或查询该持仓。"
            inferred_details["required_tool"] = "get_portfolio"
        elif "不在自选股列表" in message:
            inferred_code = "watchlist_entry_not_found"
            inferred_retryable = False
            inferred_instruction = "先调用 get_watchlist 获取当前列表，不要重复移除。"
            inferred_details["required_tool"] = "get_watchlist"
        elif "T+1" in message or "今天已交易过" in message:
            inferred_code = "order_temporarily_ineligible"
            inferred_retryable = False
            inferred_instruction = "本交易日不能完成该动作；保留计划并等待下一交易日。"
        elif "涨停" in message or "跌停" in message or "停牌" in message:
            inferred_code = "market_execution_blocked"
            inferred_retryable = False
            inferred_instruction = "当前窗口无法成交；不要在同一窗口重复提交相同订单。"
        elif "无交易总线" in message or "交易日未设置" in message:
            inferred_code = "environment_unavailable"
            inferred_retryable = False
            inferred_instruction = "环境状态异常，停止该工具调用并保留审计错误。"
        elif "盘前分析阶段不能下单" in message:
            inferred_code = "order_unavailable_in_phase"
            inferred_retryable = False
            inferred_instruction = "盘前只研究和登记候选；等待开盘窗口暴露 place_order。"
        elif "为ST股" in message:
            inferred_code = "security_ineligible"
            inferred_retryable = False
            inferred_instruction = "该证券被市场规则禁止交易；换用其他合格候选。"
        elif "禁止导入" in message or "blocked in sandbox" in message:
            inferred_code = "sandbox_disallowed_code"
            inferred_instruction = "删除被禁止的 import，改用 traderharness_api 与允许的科学计算库后重试。"
        elif "必须先用 place_order" in message:
            inferred_code = "conditional_order_cannot_open_position"
            inferred_retryable = False
            inferred_instruction = "不能用条件单绕过建仓计划；在交易窗口用 place_order 建仓。"
            inferred_details["required_tool"] = "place_order"
        elif any(token in message for token in ("未知条件单", "条件单不是活动状态", "条件单没有发生变化")):
            inferred_code = "conditional_order_state_conflict"
            inferred_instruction = "调用 list_conditional_orders 获取活动订单和当前值，再修正 order_id 或修改项。"
            inferred_details["required_tool"] = "list_conditional_orders"
        elif "持仓只数已达上限" in message or "仓位超过上限" in message:
            inferred_code = "portfolio_risk_limit"
            inferred_instruction = "调用 get_portfolio 核对组合；减小买入数量、先降低已有风险或明确放弃。"
            inferred_details["required_tool"] = "get_portfolio"

        error_code = str(raw.get("error_code") or inferred_code)
        retryable = bool(
            raw.get(
                "retryable",
                inferred_retryable and error_code not in NON_RETRYABLE_ERROR_CODES,
            )
        )
        correction = dict(raw.get("correction") or {})
        correction.setdefault("tool", tool_name)
        correction.setdefault(
            "instruction",
            inferred_instruction
            if retryable or inferred_code != default_code
            else "该错误在当前阶段不可重试；使用已有证据继续决策。",
        )
        example = tool_example(tool_name)
        if example is not None:
            correction.setdefault("valid_arguments_example", example)
        correction.setdefault("received_arguments", arguments)
        for key, value in inferred_details.items():
            correction.setdefault(key, value)
        return {
            **raw,
            "success": False,
            "error": message,
            "error_code": error_code,
            "retryable": retryable,
            "correction": correction,
        }

    async def execute(self, name: str, arguments: dict, ctx: ToolContext) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {
                "success": False,
                "error": f"未知工具: {name}",
                "error_code": "unknown_tool",
                "retryable": True,
                "correction": {"instruction": "Use a tool from the schemas supplied for this turn."},
            }
        try:
            if is_current_contract(self.contract_version):
                schema = build_current_parameters(tool.name, tool.parameters, ctx)
                issues = validate_instance(arguments, schema)
                if issues:
                    missing_fields = sorted(
                        {
                            issue["message"].removeprefix("缺少必填字段 ")
                            for issue in issues
                            if issue["message"].startswith("缺少必填字段 ")
                        }
                    )
                    return self._error_payload(
                        name,
                        arguments if isinstance(arguments, dict) else {},
                        {
                            "error": "工具参数不符合 Schema："
                            + "；".join(f"{issue['path']} {issue['message']}" for issue in issues),
                            "error_code": "invalid_tool_arguments",
                            "retryable": True,
                            "correction": {
                                "instruction": (
                                    "只修正列出的字段、类型或取值，不要改变原交易语义；使用同一工具在当前阶段重试。"
                                ),
                                "issues": issues,
                                "missing_fields": missing_fields,
                            },
                        },
                    )
            masker = ctx.entity_masker
            visible_code = arguments.get("stock_code") if isinstance(arguments, dict) else None
            candidate_resolver = getattr(masker, "masked_code_candidates", None)
            if candidate_resolver is not None and visible_code is not None:
                candidates = candidate_resolver(visible_code)
                if len(candidates) > 1:
                    result = {
                        "success": False,
                        "error": (
                            f"Masked stock code suffix '{visible_code}' is ambiguous; "
                            "use one complete board-prefixed alias."
                        ),
                        "error_code": "ambiguous_masked_stock_code",
                        "retryable": True,
                        "correction": {
                            "instruction": "Retry this tool with one exact candidate_alias.",
                            "candidate_aliases": candidates,
                        },
                    }
                    if is_current_contract(self.contract_version):
                        retry_arguments = []
                        for candidate in candidates:
                            candidate_args = dict(arguments)
                            candidate_args["stock_code"] = candidate
                            retry_arguments.append(candidate_args)
                        result["correction"].update(
                            {
                                "tool": name,
                                "received_arguments": arguments,
                                "retry_argument_choices": retry_arguments,
                                "instruction": (
                                    "根据上一条工具结果或窗口行情确定正确证券，"
                                    "从 retry_argument_choices 选择完整别名原样重试；不得猜测。"
                                ),
                            }
                        )
                    return result
            # execute_code owns the masking boundary end-to-end: its source
            # contains Agent-visible pseudocodes that the sandbox APIs unmask
            # when they are used. Rewriting embedded literals in the source
            # here would make those APIs unmask a second time and query the
            # wrong security.
            internal_arguments = (
                masker.unmask_obj(arguments) if masker is not None and not tool.handler_masks_egress else arguments
            )
            result = await tool.handler(internal_arguments, ctx)
            if tool.handler_masks_egress:
                if is_current_contract(self.contract_version):
                    if "error" in result or result.get("success") is False:
                        return self._error_payload(name, arguments, result)
                    return {"success": True, **result}
                return result
            date_masker = ctx.date_masker
            if date_masker is not None:
                result = date_masker.mask_obj(result)
            if masker is not None:
                result = masker.mask_obj(result)
                # Tool handlers are re-executed during deterministic replay;
                # new decision-card cassettes therefore use the same sanitizer
                # as live runs. Legacy demo cassettes keep their old fingerprint.
                if not ctx.replay_mode or ctx.require_decision_card:
                    result = masker.sanitize_agent_obj(result)
            if (
                getattr(ctx, "require_decision_card", False)
                and name
                in {
                    "get_stock_info",
                    "get_business_segments",
                    "get_valuation",
                    "get_kline",
                    "get_stock_price",
                    "get_announcement_evidence",
                }
                and isinstance(result, dict)
                and not result.get("error")
            ):
                visible_code = result.get("stock_code") or arguments.get("stock_code")
                if visible_code:
                    evidence = ctx.tool_call_cache.setdefault("_agent_tool_results", {})
                    by_code = evidence.setdefault(name, {})
                    by_code[str(visible_code)] = result
                    canonical_code = internal_arguments.get("stock_code")
                    if canonical_code:
                        by_code[str(canonical_code)] = result
            if is_current_contract(self.contract_version):
                if "error" in result or result.get("success") is False:
                    return self._error_payload(name, arguments, result)
                return {"success": True, **result}
            return result
        except Exception as e:
            logger.exception("tool_execution_error: %s", name)
            result = {
                "success": False,
                "error": f"工具执行失败: {type(e).__name__}: {str(e)}",
                "error_code": "tool_execution_failed",
                "retryable": True,
                "correction": {
                    "instruction": (
                        "Read the exception, correct only the tool arguments or code, and retry in the same phase."
                    )
                },
            }
            date_masker = ctx.date_masker
            if date_masker is not None:
                result = date_masker.mask_obj(result)
            masker = ctx.entity_masker
            if masker is not None:
                result = masker.mask_obj(result)
                if not ctx.replay_mode or ctx.require_decision_card:
                    result = masker.sanitize_agent_obj(result)
            if is_current_contract(self.contract_version):
                return self._error_payload(
                    name,
                    arguments if isinstance(arguments, dict) else {},
                    result,
                    default_code="tool_execution_failed",
                )
            return result

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
