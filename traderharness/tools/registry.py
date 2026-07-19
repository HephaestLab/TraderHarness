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
    date_masker: Any = None
    entity_masker: Any = None
    _bus: Any = field(default=None, repr=False)
    _workspace: Any = field(default=None, repr=False)


@dataclass
class ToolDefinition:
    """单个 tool 的定义。"""

    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], Awaitable[dict]]

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
            return {"error": f"未知工具: {name}"}
        try:
            masker = ctx.entity_masker
            internal_arguments = masker.unmask_obj(arguments) if masker is not None else arguments
            result = await tool.handler(internal_arguments, ctx)
            date_masker = ctx.date_masker
            if date_masker is not None:
                result = date_masker.mask_obj(result)
            return masker.mask_obj(result) if masker is not None else result
        except Exception as e:
            logger.exception("tool_execution_error: %s", name)
            result = {"error": f"工具执行失败: {type(e).__name__}: {str(e)}"}
            date_masker = ctx.date_masker
            if date_masker is not None:
                result = date_masker.mask_obj(result)
            masker = ctx.entity_masker
            return masker.mask_obj(result) if masker is not None else result

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
