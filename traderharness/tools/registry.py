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

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Tool 注册和分发中心。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_openai_tools_schema(self, *, exclude: set[str] | None = None) -> list[dict]:
        exclude = exclude or set()
        return [t.to_openai_schema() for t in self._tools.values() if t.name not in exclude]

    async def execute(self, name: str, arguments: dict, ctx: ToolContext) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {
                "success": False,
                "error": f"未知工具: {name}",
                "error_code": "unknown_tool",
                "retryable": True,
                "correction": {
                    "instruction": "Use a tool from the schemas supplied for this turn."
                },
            }
        try:
            masker = ctx.entity_masker
            visible_code = arguments.get("stock_code") if isinstance(arguments, dict) else None
            candidate_resolver = getattr(masker, "masked_code_candidates", None)
            if candidate_resolver is not None and visible_code is not None:
                candidates = candidate_resolver(visible_code)
                if len(candidates) > 1:
                    return {
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
            # execute_code owns the masking boundary end-to-end: its source
            # contains Agent-visible pseudocodes that the sandbox APIs unmask
            # when they are used. Rewriting embedded literals in the source
            # here would make those APIs unmask a second time and query the
            # wrong security.
            internal_arguments = (
                masker.unmask_obj(arguments)
                if masker is not None and not tool.handler_masks_egress
                else arguments
            )
            result = await tool.handler(internal_arguments, ctx)
            if tool.handler_masks_egress:
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
                        "Read the exception, correct only the tool arguments or code, "
                        "and retry in the same phase."
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
            return result

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
