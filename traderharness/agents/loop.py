"""Agent Loop — 核心三阶段 agentic 循环。

每个交易日：盘前分析 → 开盘窗口 → 尾盘窗口 → finish_day。
直接从源项目 backend/agents/agentic/agent_loop.py 迁移。
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from traderharness.agents.context import ContextManager
from traderharness.agents.llm_client import LLMClient
from traderharness.agents.memory import DailyMemory
from traderharness.tools._coerce import safe_int
from traderharness.tools.contracts import (
    CURRENT_TOOL_CONTRACT_VERSION,
    is_current_contract,
    tool_example,
)
from traderharness.tools.registry import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from traderharness.core.budget import TokenBudget
    from traderharness.core.events import EventBus
    from traderharness.trajectory.collector import TrajectoryCollector

MAX_TOOL_RESULT_CHARS = 3000
MAX_LIVE_EVENT_TEXT_CHARS = 4000


def _live_event_text(value: object) -> tuple[str, bool]:
    """Keep WebSocket/state payloads responsive; full text stays in trajectory."""
    text = str(value or "")
    if len(text) <= MAX_LIVE_EVENT_TEXT_CHARS:
        return text, False
    return text[:MAX_LIVE_EVENT_TEXT_CHARS] + "…", True


class PhaseProtocolError(RuntimeError):
    """Raised when a v5 Agent exhausts repair turns without ending its phase."""


_CORRECTION_LOCKED_ORDER_FIELDS = ("action", "stock_code", "quantity")
_CORRECTION_LOCKED_CARD_FIELDS = (
    "decision",
    "mode",
    "entry_setup",
    "theme",
    "sector_state",
    "candidate_role",
    "candidate_rank",
    "stronger_candidate_status",
    "execution_compromise",
    "market_stage",
    "extension_assessment",
)


def _validate_decision_card_correction(original: dict | None, corrected: dict) -> dict | None:
    """Prevent a format/evidence retry from becoming a new trading decision."""
    if not isinstance(original, dict):
        return None
    changed_order_fields = [
        field
        for field in _CORRECTION_LOCKED_ORDER_FIELDS
        if field in original and corrected.get(field) != original.get(field)
    ]
    original_card = original.get("decision_card")
    corrected_card = corrected.get("decision_card")
    changed_card_fields = []
    if isinstance(original_card, dict) and isinstance(corrected_card, dict):
        changed_card_fields = [
            field
            for field in _CORRECTION_LOCKED_CARD_FIELDS
            if field in original_card and corrected_card.get(field) != original_card.get(field)
        ]
    elif isinstance(original_card, dict):
        changed_card_fields = ["decision_card"]
    if not changed_order_fields and not changed_card_fields:
        return None
    return {
        "success": False,
        "error": ("受控纠错重试改变了原候选或决策卡语义，已拒绝进入撮合"),
        "error_code": "decision_card_correction_changed_semantics",
        "retryable": False,
        "correction": {
            "instruction": "保持原语义结论，等待新证据后在后续正常窗口重新决策。",
            "changed_order_fields": changed_order_fields,
            "changed_decision_card_fields": changed_card_fields,
        },
    }


_SEMANTIC_STATE_TOOLS = frozenset(
    {
        "get_portfolio",
        "get_position",
        "get_watchlist",
        "list_conditional_orders",
        "search_memory",
        "get_memory",
    }
)
_SEMANTIC_CANDIDATE_TOOLS = frozenset(
    {
        "get_stock_info",
        "get_business_segments",
        "get_valuation",
        "get_announcement_evidence",
        "get_kline",
        "get_stock_price",
    }
)
_SEMANTIC_CANDIDATE_RESEARCH_TOOLS = frozenset(
    {
        "get_stock_info",
        "get_business_segments",
        "get_valuation",
        "get_announcement_evidence",
    }
)
_SEMANTIC_PREMARKET_STAGE_REQUIREMENTS = (
    frozenset({"get_narrative_news", "get_narrative_market_overview"}),
    frozenset({"get_narrative_sector_summary"}),
    frozenset({"execute_code"}),
    frozenset(
        {
            "get_stock_info",
            "get_business_segments",
            "get_valuation",
        }
    ),
    frozenset({"add_watchlist", "remember"}),
)
_SEMANTIC_PREMARKET_STAGE_INSTRUCTIONS = (
    "Research step 1/5: identify the market causal narrative. Call both "
    "get_narrative_news and get_narrative_market_overview; do not research stocks yet.",
    "Research step 2/5: test at most two sector hypotheses. Use "
    "get_narrative_sector_summary; do not run Python or research stocks yet.",
    "Research step 3/5: use execute_code once to organize point-in-time market-wide "
    "price/volume evidence. It must produce evidence, not a buy/sell verdict.",
    "Research step 4/5: verify at most two candidate companies. You must call "
    "get_stock_info, get_business_segments, and get_valuation; use "
    "get_announcement_evidence only when a recent company-specific catalyst or "
    "invalidation needs verification. Do not repeat market-wide, sector, K-line, "
    "or current-price research.",
    "Research step 5/5: make the semantic verdict. Add only qualified candidates to "
    "the watchlist and/or remember durable conclusions. You may use get_kline and/or "
    "get_stock_price for one final review of the shortlisted candidates; after a "
    "successful review those tools are removed, so the next turn must register the "
    "verdict or explicitly abstain. Do not repeat earlier research.",
)


def _semantic_premarket_stage_instruction(
    ctx: ToolContext,
    stage_index: int,
    completed_tools: set[str] | frozenset[str] = frozenset(),
) -> str:
    if getattr(ctx, "full_market_research_allowed", None) is False:
        if stage_index == 2:
            return (
                "Monitoring step 3/4: do not run Python. Review only current positions "
                "and watchlist candidates with the supplied company, valuation, news, "
                "and price tools. Keep the candidate set small."
            )
        if stage_index == 4:
            return (
                "Monitoring step 4/4: update the watchlist or durable memory only when "
                "the evidence changed, then finish pre-market research."
            )
    if stage_index == 2:
        tool_cache = getattr(ctx, "tool_call_cache", {})
        sandbox_limit = max(0, int(getattr(ctx, "sandbox_max_calls_per_day", 0)))
        sandbox_calls = int(tool_cache.get("_sandbox_call_count", 0))
        if tool_cache.get("_sandbox_last_error") is True and sandbox_limit > sandbox_calls:
            return (
                "Research step 3/5 controlled code correction: the previous "
                "execute_code attempt failed. Read its traceback, preserve the same "
                "evidence objective, and use this one final execute_code attempt only "
                "to fix the failing code. Use documented columns and produce a compact "
                "point-in-time evidence table; do not start a new analysis. If this "
                "attempt also fails, stop code research and continue without sandbox "
                "evidence."
            )
    instruction = _SEMANTIC_PREMARKET_STAGE_INSTRUCTIONS[stage_index]
    if stage_index == 3:
        requirements = _SEMANTIC_PREMARKET_STAGE_REQUIREMENTS[stage_index]
        completed = requirements & completed_tools
        missing = requirements - completed_tools
        if completed and missing:
            instruction += (
                " Completed required tools: "
                + ", ".join(sorted(completed))
                + ". Still missing required tools: "
                + ", ".join(sorted(missing))
                + ". In this turn call every still-missing tool; do not repeat a "
                "completed tool and do not request K-line or current-price tools."
            )
    return instruction


def _semantic_premarket_allowed_tools(ctx: ToolContext, iteration_index: int) -> frozenset[str]:
    """Five-step evidence workflow; it constrains research, never the verdict."""
    stages = (
        {"get_narrative_news", "get_narrative_market_overview"},
        {"get_narrative_sector_summary", "get_narrative_news"},
        {"execute_code"}
        if getattr(ctx, "full_market_research_allowed", None) is not False
        else set(_SEMANTIC_CANDIDATE_TOOLS),
        set(_SEMANTIC_CANDIDATE_RESEARCH_TOOLS),
        {
            "add_watchlist",
            "remove_watchlist",
            "remember",
            "search_memory",
            "get_memory",
            "get_kline",
            "get_stock_price",
        },
    )
    stage = stages[min(max(0, iteration_index), len(stages) - 1)]
    return frozenset(stage) | _SEMANTIC_STATE_TOOLS


def _available_tools_instruction(available_tool_names) -> str:
    """Name the exact callable surface for this turn to prevent stale tool calls."""
    names = ", ".join(sorted(set(available_tool_names))) or "none"
    return f"Current-turn available tools (the complete list): {names}. Do not call any tool not in this list."


def _phase_protocol_instruction(ctx: ToolContext, available_tool_names) -> str:
    """Describe the current clock state and its exact callable surface."""
    phase = ctx.current_phase
    sub_window = getattr(ctx, "_current_sub_window", None)
    if phase == "pre_market":
        duty = (
            "盘前阶段：只研究和维护观察清单，禁止下单。先建立主题—板块—公司—价格阶段证据链；"
            "低位启动、趋势启动和龙头回踩都是可进入路径，不得把等待回踩设为唯一答案。"
            "研究、纠错和观察清单登记全部完成后调用 complete_phase。"
        )
    elif phase == "close_window" and sub_window == "close_2":
        duty = (
            "最后收盘阶段：可以检查证据、下单或主动放弃。先完成所有工具纠错；"
            "若持仓主题、板块扩散或龙头地位已被资金否定或资金迁往更强方向，应执行退出。"
            "全部操作完成后调用 finish_day；本阶段没有 complete_phase。"
        )
    else:
        label = {
            "open_1": "开盘前半窗口",
            "open_2": "开盘后半窗口",
            "close_1": "尾盘前半窗口",
        }.get(sub_window, phase)
        duty = (
            f"{label}：可以核验当前可见行情、管理条件单并交易。"
            "若龙头在低位启动、趋势确认或健康回踩中得到全方位证据支持，可以试仓骑乘趋势；"
            "不要求先回踩。完成本窗口的研究、交易及纠错后调用 complete_phase，"
            "市场时钟在此之前不会主动推进。"
        )
    return "【当前阶段执行协议】" + duty + "\n" + _available_tools_instruction(available_tool_names)


def _json_safe(value):
    """Replace NaN/Inf floats so tool fingerprints stay stable across runs."""
    if hasattr(value, "item") and not isinstance(value, (bytes, str, memoryview)):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _compact_result_value(value, *, list_limit: int, string_limit: int, depth: int = 0):
    if isinstance(value, str):
        return value if len(value) <= string_limit else value[:string_limit] + "…"
    if isinstance(value, list):
        return [
            _compact_result_value(
                item,
                list_limit=list_limit,
                string_limit=string_limit,
                depth=depth + 1,
            )
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        if depth >= 6:
            return {"summary": "nested object omitted"}
        return {
            key: _compact_result_value(
                item,
                list_limit=list_limit,
                string_limit=string_limit,
                depth=depth + 1,
            )
            for key, item in value.items()
        }
    return value


def _serialize_tool_result(
    result: dict,
    *,
    contract_version: str = CURRENT_TOOL_CONTRACT_VERSION,
) -> str:
    """Serialize tool result, truncating if over budget."""
    text = json.dumps(_json_safe(result), ensure_ascii=False, allow_nan=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        if not is_current_contract(contract_version):
            return text[:MAX_TOOL_RESULT_CHARS] + "... (truncated)"
        original_characters = len(text)
        for list_limit, string_limit in ((8, 240), (5, 160), (3, 100), (1, 60)):
            compacted = _compact_result_value(
                _json_safe(result),
                list_limit=list_limit,
                string_limit=string_limit,
            )
            compacted["_truncation"] = {
                "truncated": True,
                "original_characters": original_characters,
                "list_items_kept_per_array": list_limit,
                "instruction": "缩小查询范围或减少 max_results 后重试；不要猜测被省略内容。",
            }
            text = json.dumps(
                compacted,
                ensure_ascii=False,
                allow_nan=False,
                default=str,
            )
            if len(text) <= MAX_TOOL_RESULT_CHARS:
                return text
        return json.dumps(
            {
                "success": bool(result.get("success", True)),
                "_truncation": {
                    "truncated": True,
                    "original_characters": original_characters,
                    "instruction": "结果过大，必须缩小查询范围或减少 max_results 后重试。",
                },
            },
            ensure_ascii=False,
        )
    return text


logger = logging.getLogger(__name__)


@dataclass
class DayResult:
    trades: list[dict] = field(default_factory=list)
    summary: str = ""
    iterations: int = 0
    token_usage: int = 0


class AgentLoop:
    """三阶段 agentic loop — 驱动 Agent 完成一天的交易决策。"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        system_prompt: str,
        memory: DailyMemory | None = None,
        max_pre_iterations: int = 10,
        max_window_iterations: int = 3,
        token_budget: TokenBudget | None = None,
        event_bus: EventBus | None = None,
        committee=None,
    ) -> None:
        self.llm_client = llm_client
        self.registry = tool_registry
        self.system_prompt = system_prompt
        self.memory = memory
        self.max_pre_iterations = max_pre_iterations
        self.max_window_iterations = max_window_iterations
        self._context = ContextManager(max_context_tokens=60000)
        self._total_tokens: int = 0
        self._budget = token_budget
        self._event_bus = event_bus
        self.committee = committee
        self.trajectory: TrajectoryCollector | None = None
        self.remaining_trading_days: int | None = None
        self.total_trading_days: int | None = None
        # Optional cooperative cancellation used by long-running live/paper
        # sessions. Backtests and replay leave this unset, preserving their
        # historical request/action sequence exactly.
        self.cancel_check: Callable[[], bool] | None = None

    async def run_day(
        self,
        current_date: date,
        ctx: ToolContext,
        phase_barrier: Callable[[str, ToolContext], Awaitable[None]] | None = None,
    ) -> DayResult:
        """执行一个完整交易日的三阶段循环。"""
        self._context.reset()
        self._total_tokens = 0

        if self.trajectory:
            self.trajectory.start_day(current_date, {"cash": float(ctx.portfolio.cash)})

        self._context.add_message({"role": "system", "content": self.system_prompt})

        if self.memory:
            memory_text = self.memory.to_prompt_text(
                before_date=current_date,
                date_masker=getattr(ctx, "date_masker", None),
                entity_masker=getattr(ctx, "entity_masker", None),
            )
            if memory_text:
                self._context.add_message({"role": "system", "content": memory_text})

        # === Phase 1: 盘前分析 ===
        ctx.current_phase = "pre_market"
        self._emit(
            "phase_change",
            date=current_date,
            agent_id=getattr(ctx, "agent_id", ""),
            phase="pre_market",
        )
        available_tool_names = [schema["function"]["name"] for schema in self.registry.get_openai_tools_schema(ctx=ctx)]
        morning_brief = self._build_morning_brief(ctx, available_tool_names)

        # Record morning brief in trajectory
        if self.trajectory:
            self.trajectory.record_step(current_date, "morning_brief", {"content": morning_brief})
        remaining_info = ""
        if self.remaining_trading_days is not None and self.total_trading_days is not None:
            day_num = self.total_trading_days - self.remaining_trading_days
            legacy_replay_horizon = getattr(self.llm_client, "_player", None) is not None and not getattr(
                ctx, "require_decision_card", False
            )
            if legacy_replay_horizon:
                # Preserve old cassette fingerprints only. New live/recorded
                # runs never reveal the artificial end of the backtest.
                remaining_info = (
                    f"\n回测进度: 第{day_num}天/{self.total_trading_days}天"
                    f"（剩余{self.remaining_trading_days}个交易日）"
                )
            interval = max(0, int(getattr(ctx, "research_interval_days", 0)))
            if interval:
                research_day = (day_num - 1) % interval == 0
                ctx.full_market_research_allowed = research_day
                remaining_info += (
                    f"\n研究日：{'是' if research_day else '否'}（由环境计算；只有“是”时才做全市场行为特征研究）"
                )
        self._context.add_message(
            {
                "role": "user",
                "content": f"新的交易日开始。{remaining_info}\n\n{morning_brief}\n\n"
                f"现在是盘前分析阶段，你可以使用工具研究市场，但不能下单。",
            }
        )
        # Legacy cassettes fingerprinted the older schema where finish_day was
        # visible in every phase. Preserve that exact surface during replay;
        # live/new recordings expose it only in the final close phase.
        replaying = getattr(self.llm_client, "_player", None) is not None
        legacy_replaying = replaying and not getattr(ctx, "require_decision_card", False)
        early_finish_exclude = set() if legacy_replaying else {"finish_day"}
        await self._run_phase(
            ctx,
            max_iter=self.max_pre_iterations,
            exclude_tools={"place_order"} | early_finish_exclude,
        )

        window_exclude_tools = {"execute_code"} if getattr(ctx, "sandbox_pre_market_only", False) else set()
        non_final_window_exclude_tools = window_exclude_tools | early_finish_exclude

        # === Phase 2: 开盘窗口 (分两轮推进) ===
        self._flush_memory_state(ctx)
        await self._context.compress()

        from traderharness.agents.window_context import refresh_trading_window

        if phase_barrier is not None:
            await phase_barrier("open_1", ctx)
        # Rebuild focus set after pre-market watchlist mutations.
        refresh_trading_window(ctx, window="open")

        ctx.current_phase = "open_window"
        ctx._current_sub_window = "open_1"
        self._process_conditional_orders(ctx, "open_1")
        self._emit(
            "phase_change",
            date=current_date,
            agent_id=getattr(ctx, "agent_id", ""),
            phase="open_window",
        )
        if self.trajectory:
            self.trajectory.record_step(ctx.current_date, "phase_start", {"phase": "open_window"})

        # Round 1: 9:30-9:50 (前3根bar)
        half1 = self._filter_window_bars(ctx.window_minutes, 9 * 60 + 35, 9 * 60 + 50)
        window_text = self._format_window_klines(half1, "开盘窗口 前半 (9:30-9:50)", ctx.execution_price, ctx)
        window_news = self._format_window_news(ctx, "open")
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}{window_news}\n\n你现在可以下单（成交价=当前最新bar收盘价），或等待看后续走势。"
                ),
            }
        )
        await self._run_phase(
            ctx,
            max_iter=self.max_window_iterations,
            exclude_tools=non_final_window_exclude_tools,
        )

        # Round 2: 9:50-10:00 (后3根bar)
        if phase_barrier is not None:
            await phase_barrier("open_2", ctx)
            refresh_trading_window(ctx, window="open")
        ctx._current_sub_window = "open_2"
        self._process_conditional_orders(ctx, "open_2")
        half2 = self._filter_window_bars(ctx.window_minutes, 9 * 60 + 55, 10 * 60)
        window_text = self._format_window_klines(half2, "开盘窗口 后半 (9:50-10:00)", ctx.execution_price, ctx)
        self._context.add_message(
            {
                "role": "user",
                "content": (f"{window_text}\n\n开盘窗口即将结束。下单则以10:00价格成交，不下单则等尾盘。"),
            }
        )
        await self._run_phase(
            ctx,
            max_iter=self.max_window_iterations,
            exclude_tools=non_final_window_exclude_tools,
        )

        # Compress open window phase before close
        self._flush_memory_state(ctx)
        await self._context.compress()

        # === Phase 3: 尾盘窗口 (分两轮推进) ===
        # Include same-day buys and watchlist adds that happened in the open window.
        if phase_barrier is not None:
            await phase_barrier("close_1", ctx)
        refresh_trading_window(ctx, window="close")

        ctx.current_phase = "close_window"
        ctx._current_sub_window = "close_1"
        self._process_conditional_orders(ctx, "midday_close_1")
        self._emit(
            "phase_change",
            date=current_date,
            agent_id=getattr(ctx, "agent_id", ""),
            phase="close_window",
        )
        if self.trajectory:
            self.trajectory.record_step(ctx.current_date, "phase_start", {"phase": "close_window"})

        # Round 1: 14:30-14:50 (前3根bar)
        half1 = self._filter_window_bars(ctx.window_minutes, 14 * 60 + 35, 14 * 60 + 50)
        window_news = self._format_window_news(ctx, "close")
        window_text = self._format_window_klines(half1, "尾盘窗口 前半 (14:30-14:50)", ctx.execution_price, ctx)
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}{window_news}\n\n你可以下单（成交价=当前最新bar收盘价），或等待看尾盘走势。"
                ),
            }
        )
        await self._run_phase(
            ctx,
            max_iter=self.max_window_iterations,
            exclude_tools=non_final_window_exclude_tools,
        )

        # Round 2: 14:50-15:00 (后3根bar)
        if phase_barrier is not None:
            await phase_barrier("close_2", ctx)
            refresh_trading_window(ctx, window="close")
        ctx._current_sub_window = "close_2"
        self._process_conditional_orders(ctx, "close_2")
        half2 = self._filter_window_bars(ctx.window_minutes, 14 * 60 + 55, 15 * 60)
        window_text = self._format_window_klines(half2, "尾盘窗口 后半 (14:50-15:00)", ctx.execution_price, ctx)
        self._context.add_message(
            {
                "role": "user",
                "content": (f"{window_text}\n\n收盘在即。下单则以收盘价成交。操作完成后请调用 finish_day 总结今天。"),
            }
        )
        await self._run_phase(
            ctx,
            max_iter=self.max_window_iterations,
            exclude_tools=window_exclude_tools,
        )

        # 确保 finish_day 被调用
        if "finish_day_summary" in ctx.tool_call_cache:
            summary = ctx.tool_call_cache["finish_day_summary"]
        else:
            summary = await self._ensure_finish(ctx)

        # 保存记忆
        if self.memory:
            self._flush_memory_state(ctx)
            self.memory.add(
                current_date,
                summary,
                trades=ctx.trade_results,
            )

        if self.trajectory:
            reward = 0.0
            if ctx.trade_results:
                reward = sum(float(t.get("pnl", 0)) for t in ctx.trade_results)
            trajectory_actions = ctx.trade_results
            entity_masker = getattr(ctx, "entity_masker", None)
            if entity_masker is not None:
                trajectory_actions = entity_masker.mask_obj(trajectory_actions)
            self.trajectory.end_day(actions=trajectory_actions, reward=reward)

        return DayResult(
            trades=ctx.trade_results,
            summary=summary,
            iterations=self._total_tokens,
        )

    def _emit(self, event_type: str, **kwargs) -> None:
        if self._event_bus:
            self._event_bus.emit(event_type, **kwargs)

    def _flush_memory_state(self, ctx: ToolContext) -> None:
        if self.memory is None:
            return
        plans = ctx.tool_call_cache.get("_position_plans", {})
        conditions = []
        if ctx._bus is not None and hasattr(ctx._bus, "list_conditional_orders"):
            conditions = ctx._bus.list_conditional_orders(status="active")
        visible_state = {
            "position_plans": plans,
            "active_conditional_orders": conditions,
        }
        date_masker = getattr(ctx, "date_masker", None)
        entity_masker = getattr(ctx, "entity_masker", None)
        if date_masker is not None:
            visible_state = date_masker.mask_obj(visible_state)
        if entity_masker is not None:
            visible_state = entity_masker.sanitize_agent_obj(visible_state)
        self.memory.flush_runtime_state(ctx.current_date, visible_state)

    def _process_conditional_orders(self, ctx: ToolContext, window: str) -> None:
        bus = ctx._bus
        if bus is None or not hasattr(bus, "process_conditional_orders"):
            return
        outcomes = bus.process_conditional_orders(ctx.agent_id, window)
        if not outcomes:
            return
        plans = ctx.tool_call_cache.get("_position_plans", {})
        for outcome in outcomes:
            trade = outcome.get("trade")
            if not outcome.get("success") or trade is None:
                continue
            ctx.trade_results.append(trade)
            ctx.traded_today.add(trade["stock_code"])
            if trade.get("action") == "sell" and trade["stock_code"] not in ctx.portfolio.positions:
                plans.pop(trade["stock_code"], None)

        visible = outcomes
        date_masker = getattr(ctx, "date_masker", None)
        entity_masker = getattr(ctx, "entity_masker", None)
        if date_masker is not None:
            visible = date_masker.mask_obj(visible)
        if entity_masker is not None:
            visible = entity_masker.mask_obj(visible)
        self._context.add_message(
            {
                "role": "user",
                "content": "=== 环境条件单事件 ===\n"
                + _serialize_tool_result(
                    {"events": visible},
                    contract_version=self.registry.contract_version,
                ),
            }
        )
        if self.trajectory:
            self.trajectory.record_step(
                ctx.current_date,
                "conditional_order",
                {"window": window, "events": visible},
            )

    async def _run_phase(
        self,
        ctx: ToolContext,
        max_iter: int,
        exclude_tools: set[str],
    ) -> None:
        """单阶段的 tool-use loop。"""
        consecutive_errors = 0
        semantic_stage_index = 0
        semantic_stage_successes: set[str] = set()
        correction_retry_pending = False
        correction_retry_arguments: dict | None = None
        correction_required_tools: set[str] = set()
        pending_tool_corrections: dict[str, str] = {}
        phase_protocol = bool(getattr(ctx, "require_phase_completion", False))
        # The configured iteration count is the normal reasoning budget. A
        # protocol Agent gets bounded extension turns so a read, a repair, and
        # the explicit completion call cannot be cut off by the market clock.
        iteration_limit = max_iter + (8 if phase_protocol else 1)

        if self.committee is not None:
            sub_window = getattr(ctx, "_current_sub_window", None)
            memo = await self.committee.build_memo(
                self._context.get_api_messages(),
                ctx.current_phase,
                sub_window,
            )
            memo_text = memo.to_prompt()
            memo_reports = memo.reports
            date_masker = getattr(ctx, "date_masker", None)
            entity_masker = getattr(ctx, "entity_masker", None)
            if date_masker is not None:
                memo_text = date_masker.mask_text(memo_text)
                memo_reports = date_masker.mask_obj(memo_reports)
            if entity_masker is not None:
                memo_text = entity_masker.sanitize_agent_text(memo_text)
                memo_reports = entity_masker.sanitize_agent_obj(memo_reports)
            self._context.add_message({"role": "system", "content": memo_text})
            self._emit(
                "committee_memo",
                date=ctx.current_date,
                phase=ctx.current_phase,
                sub_window=sub_window,
                roles=list(memo.reports),
            )
            if self.trajectory:
                self.trajectory.record_step(
                    ctx.current_date,
                    "committee_memo",
                    {
                        "phase": ctx.current_phase,
                        "sub_window": sub_window,
                        "reports": memo_reports,
                    },
                )

        for iteration_index in range(iteration_limit):
            if self.cancel_check is not None and self.cancel_check():
                logger.info("Agent phase cancelled before LLM iteration")
                return
            is_correction_retry = correction_retry_pending
            if not phase_protocol:
                correction_retry_pending = False
            if iteration_index >= max_iter and not is_correction_retry and not phase_protocol:
                return
            if self._budget and self._budget.is_exhausted:
                logger.warning("Token budget exhausted, stopping phase")
                return

            if self._context.needs_compression():
                self._flush_memory_state(ctx)
                await self._context.compress()

            dynamic_exclude = set(exclude_tools)
            tool_cache = getattr(ctx, "tool_call_cache", {})
            if not phase_protocol:
                dynamic_exclude.add("complete_phase")
            elif ctx.current_phase == "close_window" and getattr(ctx, "_current_sub_window", None) == "close_2":
                dynamic_exclude.add("complete_phase")
            if phase_protocol and ctx.current_phase == "pre_market":
                dynamic_exclude.add("manage_conditional_order")
                if getattr(ctx, "full_market_research_allowed", None) is False:
                    dynamic_exclude.add("execute_code")
            semantic_premarket = (
                ctx.current_phase == "pre_market"
                and getattr(ctx, "require_decision_card", False)
                and not phase_protocol
            )
            if semantic_premarket:
                allowed_for_stage = _semantic_premarket_allowed_tools(ctx, semantic_stage_index)
                if semantic_stage_index in {3, 4}:
                    # Once a dossier surface succeeds, remove it from subsequent
                    # schemas so the model must finish the missing company evidence
                    # instead of repeatedly querying the same type of fact.
                    allowed_for_stage -= semantic_stage_successes
                all_names = {schema["function"]["name"] for schema in self.registry.get_openai_tools_schema(ctx=ctx)}
                dynamic_exclude.update(all_names - allowed_for_stage)
            if is_correction_retry:
                all_names = {schema["function"]["name"] for schema in self.registry.get_openai_tools_schema(ctx=ctx)}
                correction_surface = {"place_order"} | correction_required_tools
                if phase_protocol:
                    correction_surface.add("complete_phase")
                    if ctx.current_phase == "close_window" and getattr(ctx, "_current_sub_window", None) == "close_2":
                        correction_surface.discard("complete_phase")
                        correction_surface.add("finish_day")
                dynamic_exclude.update(all_names - correction_surface)
            sandbox_limit = max(0, int(getattr(ctx, "sandbox_max_calls_per_day", 0)))
            if sandbox_limit and int(tool_cache.get("_sandbox_call_count", 0)) >= sandbox_limit:
                dynamic_exclude.add("execute_code")
            if not phase_protocol and len(tool_cache.get("_narrative_sector_summary_cache", {})) >= 2:
                dynamic_exclude.add("get_narrative_sector_summary")
            if not phase_protocol and "_narrative_market_overview_payload" in tool_cache:
                dynamic_exclude.add("get_narrative_market_overview")
            if not phase_protocol and int(tool_cache.get("_narrative_news_calls", 0)) >= 2:
                dynamic_exclude.add("get_narrative_news")
            tools_schema = self.registry.get_openai_tools_schema(
                exclude=dynamic_exclude,
                ctx=ctx,
            )
            if getattr(self.llm_client, "_player", None) is not None and not getattr(
                ctx, "require_decision_card", False
            ):
                # The bundled v2 demo cassette predates the optional semantic
                # decision_card property. Runtime validation is disabled for
                # that legacy Agent, so reproduce its exact function schema.
                tools_schema = copy.deepcopy(tools_schema)
                for schema in tools_schema:
                    function = schema.get("function", {})
                    if function.get("name") != "place_order":
                        continue
                    properties = function.get("parameters", {}).get("properties", {})
                    properties.pop("decision_card", None)
            available_tool_names = {schema["function"]["name"] for schema in tools_schema}

            request_messages = self._context.get_api_messages()
            if phase_protocol:
                request_messages = [
                    *request_messages,
                    {
                        "role": "system",
                        "content": _phase_protocol_instruction(ctx, available_tool_names),
                    },
                ]
            if semantic_premarket:
                request_messages = [
                    *request_messages,
                    {
                        "role": "system",
                        "content": (
                            _semantic_premarket_stage_instruction(ctx, semantic_stage_index, semantic_stage_successes)
                            + "\n\n"
                            + _available_tools_instruction(available_tool_names)
                        ),
                    },
                ]
            if is_correction_retry:
                missing_instruction = ""
                if correction_required_tools:
                    missing_instruction = (
                        " 当前仍缺少同一候选的成功工具证据："
                        + ", ".join(sorted(correction_required_tools))
                        + "。先调用这些工具；可在同一响应中于读取后重交 place_order。"
                    )
                request_messages = [
                    *request_messages,
                    {
                        "role": "system",
                        "content": (
                            "【受控纠错重试】上一次 place_order 未进入撮合。"
                            "严格按照紧邻的 tool 错误中 correction 指令，"
                            "只修正字段层级、缺失字段、数据类型或证据ID。"
                            "不得改变 decision、mode、sector_state、candidate_role、"
                            "candidate_rank、stronger_candidate_status、"
                            "execution_compromise 或 extension_assessment 等语义结论。"
                            + missing_instruction
                            + "证据齐全后重新提交同一候选的 place_order；"
                            "若新行情使原结论失效，则主动调用阶段结束工具并明确放弃。"
                        ),
                    },
                ]
            response = await self.llm_client.chat(
                messages=request_messages,
                tools=tools_schema,
            )
            # A cancellation may arrive while the remote model request is in
            # flight. Preserve the returned response in the audit trail, but do
            # not execute tool calls (especially orders) after a safe stop.
            discarded_after_cancel = bool(
                self.cancel_check is not None and self.cancel_check()
            )
            # Cassette outputs are already date/entity-sanitized at record time.
            # Re-sanitizing during replay is not idempotent (alias / code rewrites
            # drift) and poisons subsequent request fingerprints.
            is_replay = getattr(self.llm_client, "_player", None) is not None
            if not is_replay:
                date_masker = getattr(ctx, "date_masker", None)
                entity_masker = getattr(ctx, "entity_masker", None)
                if response.get("content"):
                    if date_masker is not None:
                        response["content"] = date_masker.mask_text(response["content"])
                    if entity_masker is not None:
                        response["content"] = entity_masker.sanitize_agent_text(response["content"])
                if response.get("reasoning_content"):
                    if date_masker is not None:
                        response["reasoning_content"] = date_masker.mask_text(response["reasoning_content"])
                    if entity_masker is not None:
                        response["reasoning_content"] = entity_masker.sanitize_agent_text(response["reasoning_content"])
                if date_masker is not None or entity_masker is not None:
                    for tool_call in response.get("tool_calls") or []:
                        raw_arguments = tool_call["function"].get("arguments", "")
                        try:
                            parsed_arguments = json.loads(raw_arguments)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if date_masker is not None:
                            parsed_arguments = date_masker.mask_obj(parsed_arguments)
                        if entity_masker is not None:
                            parsed_arguments = entity_masker.sanitize_agent_obj(parsed_arguments)
                        tool_call["function"]["arguments"] = json.dumps(
                            parsed_arguments,
                            ensure_ascii=False,
                        )
            record_replay_call = getattr(self.llm_client, "record_replay_call", None)
            if record_replay_call is not None:
                record_replay_call(
                    messages=request_messages,
                    tools=tools_schema,
                    output=response,
                )
            if self.trajectory:
                self.trajectory.record_step(
                    ctx.current_date,
                    "llm_exchange",
                    {
                        "phase": ctx.current_phase,
                        "sub_window": getattr(ctx, "_current_sub_window", None),
                        "messages": copy.deepcopy(request_messages),
                        "tools": copy.deepcopy(tools_schema),
                        "response": copy.deepcopy(response),
                        "discarded_after_cancel": discarded_after_cancel,
                    },
                )
            live_content, content_truncated = _live_event_text(response.get("content"))
            live_reasoning, reasoning_truncated = _live_event_text(
                response.get("reasoning_content")
            )
            self._emit(
                "llm_response",
                date=ctx.current_date,
                agent_id=getattr(ctx, "agent_id", ""),
                phase=ctx.current_phase,
                has_tool_calls=bool(response.get("tool_calls")),
                tokens=response.get("_usage", {}).get("total_tokens", 0),
                content=live_content,
                reasoning_content=live_reasoning,
                content_truncated=content_truncated,
                reasoning_truncated=reasoning_truncated,
                discarded_after_cancel=discarded_after_cancel,
            )
            if discarded_after_cancel:
                usage = response.get("_usage", {})
                tokens = usage.get("total_tokens", 0) if usage else 0
                self._total_tokens += tokens
                if self._budget and tokens:
                    self._budget.consume(tokens)
                logger.info("Agent phase cancelled after LLM response; output audited and discarded")
                return

            assistant_content = response.get("content", "") or ""
            assistant_dict = {"role": "assistant", "content": assistant_content}
            if response.get("reasoning_content"):
                assistant_dict["reasoning_content"] = response["reasoning_content"]
            if response.get("tool_calls"):
                assistant_dict["tool_calls"] = response["tool_calls"]
            self._context.add_message(assistant_dict)

            # Record assistant response in trajectory
            if self.trajectory and assistant_content:
                assistant_record = {
                    "content": assistant_content,
                    "phase": ctx.current_phase,
                    "sub_window": getattr(ctx, "_current_sub_window", None),
                }
                if response.get("reasoning_content"):
                    assistant_record["reasoning_content"] = response["reasoning_content"]
                if response.get("tool_calls"):
                    assistant_record["tool_calls"] = copy.deepcopy(response["tool_calls"])
                self.trajectory.record_step(
                    ctx.current_date,
                    "assistant",
                    assistant_record,
                )

            usage = response.get("_usage", {})
            if usage:
                tokens = usage.get("total_tokens", 0)
                self._total_tokens += tokens
                if self._budget:
                    self._budget.consume(tokens)

            if not response.get("tool_calls"):
                # Max output recovery: if truncated, retry once with no tool constraint
                finish_reason = response.get("_finish_reason", "")
                if finish_reason == "length" and not response.get("content"):
                    logger.warning("Output truncated, skipping retry (empty content)")
                if phase_protocol:
                    self._context.add_message(
                        {
                            "role": "user",
                            "content": (
                                "当前阶段尚未由工具显式结束。请完成尚未完成的工具纠错，"
                                "然后调用 complete_phase；若是最后收盘阶段则调用 finish_day。"
                            ),
                        }
                    )
                    continue
                break

            should_finish = False
            completion_arguments: dict = {}
            correction_retry_requested = False
            correction_order_calls = 0
            iteration_had_error = False
            iteration_had_success = False
            iteration_blocking_errors: set[str] = set()
            # Partition: the historical read-then-write message order is part of
            # the replay fingerprint. Keep that ordering, but execute each batch
            # serially (concurrent gather previously raced on shared frames).
            # Import lazily to avoid a module cycle while keeping tool access
            # semantics in one auditable catalog.
            from traderharness.agents.tool_agent import READ_ONLY_TOOL_NAMES

            read_only_tool_names = set(READ_ONLY_TOOL_NAMES)
            if not is_current_contract(self.registry.contract_version):
                # v1-v4 classified these two tools as stateful. Preserve that
                # historical message ordering and serializer for replay hashes.
                read_only_tool_names.difference_update({"screen_stocks", "screen_behavioral_cycle"})

            parsed_calls = []
            for tc in response["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError) as exc:
                    if is_current_contract(self.registry.contract_version):
                        parse_result = {
                            "success": False,
                            "error": f"工具参数不是合法 JSON：{exc}",
                            "error_code": "invalid_tool_arguments_json",
                            "retryable": True,
                            "correction": {
                                "tool": tool_name,
                                "instruction": (
                                    "输出一个完整 JSON object；不要使用 Markdown 代码块、"
                                    "尾随逗号或注释，然后在当前阶段重试。"
                                ),
                                "valid_arguments_example": tool_example(tool_name),
                                "received_arguments_fragment": str(tc["function"].get("arguments", ""))[:500],
                            },
                        }
                    else:
                        parse_result = {"error": "参数解析失败，请检查JSON格式"}
                    if is_current_contract(self.registry.contract_version):
                        pending_tool_corrections[tool_name] = str(parse_result["error_code"])
                        iteration_blocking_errors.add(str(parse_result["error_code"]))
                    self._context.add_message(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(parse_result, ensure_ascii=False),
                        }
                    )
                    iteration_had_error = True
                    continue
                if tool_name not in available_tool_names:
                    if is_current_contract(self.registry.contract_version) or getattr(
                        ctx, "require_decision_card", False
                    ):
                        result = {
                            "success": False,
                            "error": (
                                f"Tool '{tool_name}' is unavailable in the current "
                                "phase or research stage. " + _available_tools_instruction(available_tool_names)
                            ),
                            "error_code": "tool_unavailable_in_phase",
                            "retryable": True,
                            "available_tools": sorted(available_tool_names),
                            "correction": {
                                "instruction": (
                                    "Use one of available_tools in this same phase, then "
                                    "retry the intended action before completing the phase."
                                ),
                                "phase": ctx.current_phase,
                                "sub_window": getattr(ctx, "_current_sub_window", None),
                            },
                        }
                    else:
                        # Preserve the legacy tool-result fingerprint used by
                        # bundled demo cassettes.
                        result = {
                            "error": (
                                f"Tool '{tool_name}' is unavailable in the current "
                                "phase or research stage. Use only the supplied tool schemas."
                            )
                        }
                    self._emit(
                        "tool_call",
                        date=ctx.current_date,
                        agent_id=getattr(ctx, "agent_id", ""),
                        tool=tool_name,
                        args=arguments,
                        success=False,
                    )
                    if self.trajectory:
                        self.trajectory.record_step(
                            ctx.current_date,
                            "tool_call",
                            {
                                "id": tc["id"],
                                "name": tool_name,
                                "args": arguments,
                                "result": result,
                                "phase": ctx.current_phase,
                                "sub_window": getattr(ctx, "_current_sub_window", None),
                            },
                        )
                    self._context.add_message(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    iteration_had_error = True
                    if result.get("retryable") is True:
                        unavailable_code = str(result.get("error_code") or "tool_unavailable_in_phase")
                        iteration_blocking_errors.add(unavailable_code)
                        if is_current_contract(self.registry.contract_version):
                            pending_tool_corrections[tool_name] = unavailable_code
                    continue
                parsed_calls.append((tc, tool_name, arguments))

            read_batch = [(tc, name, args) for tc, name, args in parsed_calls if name in read_only_tool_names]
            write_batch = [(tc, name, args) for tc, name, args in parsed_calls if name not in read_only_tool_names]

            async def _run_tool(tc, tool_name, arguments, *, read_only: bool) -> None:
                nonlocal should_finish, iteration_had_error, iteration_had_success
                nonlocal completion_arguments
                nonlocal correction_retry_requested, correction_retry_arguments
                nonlocal correction_order_calls, correction_retry_pending
                completion_tool = tool_name in {"finish_day", "complete_phase"}
                if completion_tool:
                    completion_arguments = dict(arguments)
                if completion_tool and not is_current_contract(self.registry.contract_version):
                    should_finish = True
                    if tool_name == "finish_day":
                        ctx.tool_call_cache["finish_day_summary"] = arguments.get("summary", "")
                    else:
                        sub_window = getattr(ctx, "_current_sub_window", None)
                        phase_key = f"{ctx.current_phase}:{sub_window or ctx.current_phase}"
                        ctx.tool_call_cache.setdefault("_completed_phases", {})[phase_key] = copy.deepcopy(arguments)

                correction_guard = None
                if is_correction_retry and tool_name == "place_order":
                    correction_order_calls += 1
                    if correction_order_calls > 1:
                        correction_guard = {
                            "success": False,
                            "error": "受控纠错窗口只允许一次 place_order",
                            "error_code": "decision_card_correction_retry_limit",
                            "retryable": False,
                        }
                    else:
                        correction_guard = _validate_decision_card_correction(correction_retry_arguments, arguments)
                result = correction_guard or await self.registry.execute(tool_name, arguments, ctx)
                if (
                    is_current_contract(self.registry.contract_version)
                    and completion_tool
                    and "error" not in result
                    and result.get("success") is not False
                ):
                    should_finish = True
                    if tool_name == "finish_day":
                        ctx.tool_call_cache["finish_day_summary"] = arguments.get("summary", "")
                    else:
                        sub_window = getattr(ctx, "_current_sub_window", None)
                        phase_key = f"{ctx.current_phase}:{sub_window or ctx.current_phase}"
                        ctx.tool_call_cache.setdefault("_completed_phases", {})[phase_key] = copy.deepcopy(arguments)
                correction_count = int(tool_cache.get("_decision_card_correction_retries", 0))
                if (
                    tool_name == "place_order"
                    and result.get("retryable") is True
                    and result.get("retry_kind") == "decision_card_correction"
                    and (not is_correction_retry or phase_protocol)
                    and correction_count < (6 if phase_protocol else 2)
                ):
                    correction_retry_requested = True
                    if correction_retry_arguments is None:
                        correction_retry_arguments = copy.deepcopy(arguments)
                    correction = result.get("correction") or {}
                    correction_required_tools.update(
                        str(name)
                        for name in correction.get("missing_tools", [])
                        if self.registry.get_tool(str(name)) is not None
                    )
                if (
                    phase_protocol
                    and is_correction_retry
                    and tool_name in correction_required_tools
                    and "error" not in result
                ):
                    correction_required_tools.discard(tool_name)
                self._emit(
                    "tool_call",
                    date=ctx.current_date,
                    agent_id=getattr(ctx, "agent_id", ""),
                    tool=tool_name,
                    args=arguments,
                    success="error" not in result,
                    error=result.get("error"),
                    error_code=result.get("error_code"),
                )
                if self.trajectory:
                    self.trajectory.record_step(
                        ctx.current_date,
                        "tool_call",
                        {
                            "id": tc["id"],
                            "name": tool_name,
                            "args": arguments,
                            "result": result,
                            "phase": ctx.current_phase,
                            "sub_window": getattr(ctx, "_current_sub_window", None),
                        },
                    )
                # Keep the historical serializers: read-only tools used the
                # truncated JSON helper; write/stateful tools used raw dumps.
                # Mixing them is load-bearing for fingerprinted cassettes.
                content = (
                    _serialize_tool_result(
                        result,
                        contract_version=self.registry.contract_version,
                    )
                    if read_only
                    else json.dumps(result, ensure_ascii=False, default=str)
                )
                self._context.add_message(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": content,
                    }
                )
                sandbox_attempts_exhausted = (
                    tool_name == "execute_code"
                    and "error" in result
                    and (sandbox_limit <= 0 or int(tool_cache.get("_sandbox_call_count", 0)) >= sandbox_limit)
                )
                usable_stage_evidence = "error" not in result or sandbox_attempts_exhausted
                if semantic_premarket and usable_stage_evidence:
                    semantic_stage_successes.add(tool_name)
                if (
                    semantic_premarket
                    and tool_name == "execute_code"
                    and "error" in result
                    and sandbox_limit
                    and int(tool_cache.get("_sandbox_call_count", 0)) < sandbox_limit
                ):
                    retry_count = int(tool_cache.get("_sandbox_retry_count", 0)) + 1
                    tool_cache["_sandbox_retry_count"] = retry_count
                    self._emit(
                        "sandbox_retry",
                        date=ctx.current_date,
                        agent_id=getattr(ctx, "agent_id", ""),
                        phase=ctx.current_phase,
                        retry_count=retry_count,
                    )
                    if self.trajectory:
                        self.trajectory.record_step(
                            ctx.current_date,
                            "sandbox_retry",
                            {
                                "phase": ctx.current_phase,
                                "sub_window": getattr(ctx, "_current_sub_window", None),
                                "retry_count": retry_count,
                                "scope": "traceback_code_correction_only",
                            },
                        )
                if "error" in result:
                    iteration_had_error = True
                    if is_current_contract(self.registry.contract_version):
                        error_code = str(result.get("error_code") or "tool_rejected")
                        if result.get("retryable") is True:
                            pending_tool_corrections[tool_name] = error_code
                            iteration_blocking_errors.add(error_code)
                        else:
                            pending_tool_corrections.pop(tool_name, None)
                else:
                    iteration_had_success = True
                    pending_tool_corrections.pop(tool_name, None)

            for tc, name, args in read_batch:
                await _run_tool(tc, name, args, read_only=True)
            for tc, name, args in write_batch:
                await _run_tool(tc, name, args, read_only=False)

            # "Consecutive errors" means consecutive LLM/tool rounds, not the
            # number of parallel calls in one response. A batch of four invalid
            # calls is one failed correction opportunity, not four failed turns.
            if iteration_had_success:
                consecutive_errors = 0
            elif iteration_had_error:
                consecutive_errors += 1

            if correction_retry_requested:
                if is_current_contract(self.registry.contract_version) and should_finish:
                    phase_key = f"{ctx.current_phase}:{getattr(ctx, '_current_sub_window', None) or ctx.current_phase}"
                    ctx.tool_call_cache.get("_completed_phases", {}).pop(
                        phase_key,
                        None,
                    )
                    ctx.tool_call_cache.pop("finish_day_summary", None)
                    should_finish = False
                retry_count = int(tool_cache.get("_decision_card_correction_retries", 0)) + 1
                tool_cache["_decision_card_correction_retries"] = retry_count
                correction_retry_pending = True
                self._emit(
                    "decision_card_retry",
                    date=ctx.current_date,
                    agent_id=getattr(ctx, "agent_id", ""),
                    phase=ctx.current_phase,
                    retry_count=retry_count,
                )
                if self.trajectory:
                    self.trajectory.record_step(
                        ctx.current_date,
                        "decision_card_retry",
                        {
                            "phase": ctx.current_phase,
                            "sub_window": getattr(ctx, "_current_sub_window", None),
                            "retry_count": retry_count,
                            "scope": "format_and_evidence_only",
                        },
                    )
                continue

            if should_finish:
                if is_current_contract(self.registry.contract_version):
                    abandoned = {str(code) for code in completion_arguments.get("abandon_error_codes", [])}
                    pending_tool_corrections = {
                        tool_name: error_code
                        for tool_name, error_code in pending_tool_corrections.items()
                        if error_code not in abandoned
                    }
                    if pending_tool_corrections or iteration_blocking_errors - abandoned:
                        should_finish = False
                        phase_key = (
                            f"{ctx.current_phase}:{getattr(ctx, '_current_sub_window', None) or ctx.current_phase}"
                        )
                        ctx.tool_call_cache.get("_completed_phases", {}).pop(
                            phase_key,
                            None,
                        )
                        ctx.tool_call_cache.pop("finish_day_summary", None)
                        pending_text = ", ".join(
                            f"{tool}={code}" for tool, code in sorted(pending_tool_corrections.items())
                        )
                        self._context.add_message(
                            {
                                "role": "system",
                                "content": (
                                    "阶段未结束：仍有待处理的可重试工具错误："
                                    + (pending_text or ", ".join(sorted(iteration_blocking_errors)))
                                    + "。按 correction 重试成功；若明确放弃该动作，"
                                    "在阶段结束工具的 abandon_error_codes 中列出对应 error_code，"
                                    "并在 summary 说明原因。"
                                ),
                            }
                        )
                        continue
                correction_retry_pending = False
                correction_required_tools.clear()
                return

            if phase_protocol and is_correction_retry:
                # Reading missing evidence is part of the same correction
                # transaction. Keep this clock phase open until the corrected
                # order is submitted, or the Agent explicitly abandons it.
                if correction_order_calls == 0:
                    correction_retry_pending = True
                    continue
                correction_retry_pending = False
                correction_retry_arguments = None
                correction_required_tools.clear()

            if semantic_premarket:
                requirements = _SEMANTIC_PREMARKET_STAGE_REQUIREMENTS[semantic_stage_index]
                if semantic_stage_index == 2 and getattr(ctx, "full_market_research_allowed", None) is False:
                    requirements = frozenset(_SEMANTIC_CANDIDATE_TOOLS)
                stage_complete = requirements <= semantic_stage_successes
                if semantic_stage_index in {2, 4}:
                    stage_complete = bool(requirements & semantic_stage_successes)
                if stage_complete:
                    if semantic_stage_index == len(_SEMANTIC_PREMARKET_STAGE_REQUIREMENTS) - 1:
                        return
                    if semantic_stage_index == 2 and getattr(ctx, "full_market_research_allowed", None) is False:
                        semantic_stage_index = 4
                    else:
                        semantic_stage_index += 1
                    semantic_stage_successes.clear()

            if should_finish or (consecutive_errors >= 3 and not phase_protocol):
                return

        if phase_protocol:
            logger.warning(
                "Phase completion extension exhausted: phase=%s sub_window=%s",
                ctx.current_phase,
                getattr(ctx, "_current_sub_window", None),
            )
            if self.trajectory:
                self.trajectory.record_step(
                    ctx.current_date,
                    (
                        "phase_protocol_failure"
                        if is_current_contract(self.registry.contract_version)
                        else "phase_forced_complete"
                    ),
                    {
                        "phase": ctx.current_phase,
                        "sub_window": getattr(ctx, "_current_sub_window", None),
                        "reason": "completion_extension_exhausted",
                    },
                )
            if is_current_contract(self.registry.contract_version):
                failure = {
                    "phase": ctx.current_phase,
                    "sub_window": getattr(ctx, "_current_sub_window", None),
                    "error_code": "phase_completion_protocol_exhausted",
                    "pending_tool_corrections": dict(pending_tool_corrections),
                }
                ctx.tool_call_cache["_phase_protocol_failure"] = failure
                raise PhaseProtocolError(
                    "Agent 未在纠错预算内成功调用阶段结束工具；"
                    f"phase={failure['phase']} sub_window={failure['sub_window']} "
                    f"pending={failure['pending_tool_corrections']}"
                )

    async def _ensure_finish(self, ctx: ToolContext) -> str:
        """确保 Agent 调用了 finish_day。"""
        self._context.add_message(
            {
                "role": "user",
                "content": "收盘了。请调用 finish_day 写下今天的总结。",
            }
        )

        finish_tool = self.registry.get_tool("finish_day")
        if finish_tool is None:
            return "（无 finish_day 工具）"

        if is_current_contract(self.registry.contract_version):
            return await self._ensure_finish_current(ctx, finish_tool)

        tools_schema = [
            finish_tool.to_openai_schema(
                contract_version=self.registry.contract_version,
                ctx=ctx,
            )
        ]
        request_messages = self._context.get_api_messages()
        response = await self.llm_client.chat(
            messages=request_messages,
            tools=tools_schema,
        )
        date_masker = getattr(ctx, "date_masker", None)
        entity_masker = getattr(ctx, "entity_masker", None)
        for key in ("content", "reasoning_content"):
            if not response.get(key):
                continue
            if date_masker is not None:
                response[key] = date_masker.mask_text(response[key])
            if entity_masker is not None:
                response[key] = entity_masker.sanitize_agent_text(response[key])
        for tool_call in response.get("tool_calls") or []:
            raw_arguments = tool_call["function"].get("arguments", "")
            try:
                parsed_arguments = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError):
                continue
            if date_masker is not None:
                parsed_arguments = date_masker.mask_obj(parsed_arguments)
            if entity_masker is not None:
                parsed_arguments = entity_masker.sanitize_agent_obj(parsed_arguments)
            tool_call["function"]["arguments"] = json.dumps(
                parsed_arguments,
                ensure_ascii=False,
            )
        record_replay_call = getattr(self.llm_client, "record_replay_call", None)
        if record_replay_call is not None:
            record_replay_call(
                messages=request_messages,
                tools=tools_schema,
                output=response,
            )
        if self.trajectory:
            self.trajectory.record_step(
                ctx.current_date,
                "llm_exchange",
                {
                    "phase": ctx.current_phase,
                    "sub_window": getattr(ctx, "_current_sub_window", None),
                    "messages": copy.deepcopy(request_messages),
                    "tools": copy.deepcopy(tools_schema),
                    "response": copy.deepcopy(response),
                },
            )

        summary = ""
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["function"]["name"] == "finish_day":
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        summary = args.get("summary", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif response.get("content"):
            summary = response["content"]

        if summary:
            if date_masker is not None:
                summary = date_masker.mask_text(summary)
            if entity_masker is not None:
                summary = entity_masker.sanitize_agent_text(summary)
        return summary or "（Agent 未提供当日总结）"

    async def _ensure_finish_current(self, ctx: ToolContext, finish_tool) -> str:
        """Require a valid ``finish_day`` call and expose every repair attempt."""
        tools_schema = [
            finish_tool.to_openai_schema(
                contract_version=self.registry.contract_version,
                ctx=ctx,
            )
        ]
        last_error_code = "finish_day_not_called"

        for attempt in range(1, 4):
            request_messages = self._context.get_api_messages()
            response = await self.llm_client.chat(
                messages=request_messages,
                tools=tools_schema,
            )
            is_replay = getattr(self.llm_client, "_player", None) is not None
            date_masker = getattr(ctx, "date_masker", None)
            entity_masker = getattr(ctx, "entity_masker", None)
            if not is_replay:
                for key in ("content", "reasoning_content"):
                    if not response.get(key):
                        continue
                    if date_masker is not None:
                        response[key] = date_masker.mask_text(response[key])
                    if entity_masker is not None:
                        response[key] = entity_masker.sanitize_agent_text(response[key])
                for tool_call in response.get("tool_calls") or []:
                    raw_arguments = tool_call["function"].get("arguments", "")
                    try:
                        parsed_arguments = json.loads(raw_arguments)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if date_masker is not None:
                        parsed_arguments = date_masker.mask_obj(parsed_arguments)
                    if entity_masker is not None:
                        parsed_arguments = entity_masker.sanitize_agent_obj(parsed_arguments)
                    tool_call["function"]["arguments"] = json.dumps(
                        parsed_arguments,
                        ensure_ascii=False,
                    )

            record_replay_call = getattr(self.llm_client, "record_replay_call", None)
            if record_replay_call is not None:
                record_replay_call(
                    messages=request_messages,
                    tools=tools_schema,
                    output=response,
                )
            if self.trajectory:
                self.trajectory.record_step(
                    ctx.current_date,
                    "llm_exchange",
                    {
                        "phase": ctx.current_phase,
                        "sub_window": getattr(ctx, "_current_sub_window", None),
                        "messages": copy.deepcopy(request_messages),
                        "tools": copy.deepcopy(tools_schema),
                        "response": copy.deepcopy(response),
                        "finish_repair_attempt": attempt,
                    },
                )

            assistant_message = {
                "role": "assistant",
                "content": response.get("content", "") or "",
            }
            if response.get("reasoning_content"):
                assistant_message["reasoning_content"] = response["reasoning_content"]
            if response.get("tool_calls"):
                assistant_message["tool_calls"] = response["tool_calls"]
            self._context.add_message(assistant_message)

            usage = response.get("_usage", {})
            if usage:
                tokens = usage.get("total_tokens", 0)
                self._total_tokens += tokens
                if self._budget:
                    self._budget.consume(tokens)

            finish_calls = [
                call
                for call in response.get("tool_calls") or []
                if call.get("function", {}).get("name") == "finish_day"
            ]
            if not finish_calls:
                repair_result = {
                    "success": False,
                    "error": "收盘阶段必须显式调用 finish_day，普通文本不能结束交易日。",
                    "error_code": "finish_day_not_called",
                    "retryable": True,
                    "correction": {
                        "instruction": "立即按有效示例调用 finish_day。",
                        "valid_arguments_example": tool_example("finish_day"),
                        "attempt": attempt,
                    },
                }
                last_error_code = repair_result["error_code"]
                self._context.add_message({"role": "system", "content": json.dumps(repair_result, ensure_ascii=False)})
                continue

            call = finish_calls[0]
            raw_arguments = call["function"].get("arguments", "")
            call_arguments: dict = {}
            try:
                call_arguments = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                result = {
                    "success": False,
                    "error": f"finish_day 参数不是合法 JSON：{exc}",
                    "error_code": "invalid_tool_arguments_json",
                    "retryable": True,
                    "correction": {
                        "instruction": "输出完整 JSON object 后重试 finish_day。",
                        "valid_arguments_example": tool_example("finish_day"),
                        "received_arguments_fragment": str(raw_arguments)[:500],
                    },
                }
            else:
                result = await self.registry.execute("finish_day", call_arguments, ctx)

            self._context.add_message(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", f"finish-repair-{attempt}"),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
            self._emit(
                "tool_call",
                date=ctx.current_date,
                agent_id=getattr(ctx, "agent_id", ""),
                tool="finish_day",
                args=call_arguments,
                success=result.get("success") is True,
            )
            if self.trajectory:
                self.trajectory.record_step(
                    ctx.current_date,
                    "tool_call",
                    {
                        "id": call.get("id"),
                        "name": "finish_day",
                        "args": call_arguments,
                        "result": result,
                        "phase": ctx.current_phase,
                        "sub_window": getattr(ctx, "_current_sub_window", None),
                        "finish_repair_attempt": attempt,
                    },
                )
            if result.get("success") is True:
                summary = str(result.get("summary") or call_arguments.get("summary") or "")
                ctx.tool_call_cache["finish_day_summary"] = summary
                return summary

            last_error_code = str(result.get("error_code") or "finish_day_rejected")
            self._context.add_message(
                {
                    "role": "system",
                    "content": (
                        "finish_day 尚未成功，不能用普通文本结束。读取紧邻工具结果的 correction，并在本阶段重试。"
                    ),
                }
            )

        summary = f"（finish_day 三次纠错失败：{last_error_code}）"
        ctx.tool_call_cache["finish_day_summary"] = summary
        ctx.tool_call_cache["_finish_day_protocol_failure"] = {
            "error_code": last_error_code,
            "attempts": 3,
        }
        if self.trajectory:
            self.trajectory.record_step(
                ctx.current_date,
                "finish_day_protocol_failure",
                {"error_code": last_error_code, "attempts": 3},
            )
        return summary

    @staticmethod
    def _build_morning_brief(ctx: ToolContext, available_tool_names: list[str] | None = None) -> str:
        """从已有数据生成晨报。包含持仓涨跌、总收益率、板块概览、P0公告、P1政策。"""
        lines = ["=== 市场晨报 ==="]

        # 总资产与收益率 — 盘前只能用昨收，禁止用当日开盘窗成交价（防前视）。
        from traderharness.agents.window_context import previous_close_prices

        prices = previous_close_prices(ctx)
        total_value = float(ctx.portfolio.total_value(prices)) if prices else float(ctx.portfolio.cash)
        initial = float(ctx.initial_cash)
        return_pct = ((total_value - initial) / initial * 100) if initial > 0 else 0.0
        lines.append(f"\n总资产: {total_value:,.0f}元 | 累计收益: {return_pct:+.2f}%")

        # Corporate actions today
        corporate_actions = ctx.tool_call_cache.get("_corporate_actions", [])
        if corporate_actions:
            lines.append("\n=== 持仓提醒 ===")
            for action in corporate_actions:
                lines.append(f"  {action['stock_code']}: 今日除权 — {action['description']}")
                if "cash_dividend" in action:
                    lines.append(f"    到账现金: {action['cash_dividend']:.2f}元")

        # 持仓概况 + 昨日涨跌 + 浮盈
        positions = ctx.portfolio.positions
        cash = float(ctx.portfolio.cash)
        if positions:
            lines.append(f"\n持仓: {len(positions)}只 | 可用资金: {cash:,.0f}元")
            for code, pos in positions.items():
                change_str = ""
                daily = ctx.preloaded_daily.get(code)
                if daily is not None and not daily.empty:
                    filtered = daily[daily["date"] < ctx.current_date]
                    if len(filtered) >= 2:
                        last_close = float(filtered.iloc[-1]["close"])
                        prev_close = float(filtered.iloc[-2]["close"])
                        pct = (last_close - prev_close) / prev_close * 100
                        change_str = f" 昨日{pct:+.2f}%"
                pnl_str = ""
                price = prices.get(code)
                if price:
                    pnl = (float(price) - float(pos.avg_cost)) / float(pos.avg_cost) * 100
                    pnl_str = f" 浮盈{pnl:+.1f}%"
                # Suspension check
                today_data = ctx.preloaded_daily.get(code)
                suspended = False
                if today_data is not None and not today_data.empty:
                    today_row = today_data[today_data["date"] == ctx.current_date]
                    if today_row.empty:
                        suspended = True
                suspend_str = " ⚠️停牌" if suspended else ""
                lines.append(
                    f"  {code}: {pos.quantity}股, 成本{float(pos.avg_cost):.2f}{change_str}{pnl_str}{suspend_str}"
                )
        else:
            lines.append(f"\n当前空仓 | 可用资金: {cash:,.0f}元")

        # 板块涨跌概览（按行业聚合）
        import bisect

        from traderharness.data.stock_registry_loader import get_stock_industry

        sector_changes: dict[str, list[float]] = {}
        total_up = 0
        total_down = 0
        for code, df in ctx.preloaded_daily.items():
            if df is None or df.empty or len(df) < 2:
                continue
            dates = df["date"].tolist()
            idx = bisect.bisect_left(dates, ctx.current_date)
            if idx < 2:
                continue
            last = float(df.iloc[idx - 1]["close"])
            prev = float(df.iloc[idx - 2]["close"])
            if prev == 0:
                continue
            change = (last - prev) / prev * 100
            if change > 0:
                total_up += 1
            elif change < 0:
                total_down += 1
            industry = get_stock_industry(code)
            if industry not in sector_changes:
                sector_changes[industry] = []
            sector_changes[industry].append(change)

        if sector_changes:
            lines.append(f"\n昨日全市场({total_up + total_down}只): 上涨{total_up} 下跌{total_down}")
            sector_avg = {s: sum(v) / len(v) for s, v in sector_changes.items() if len(v) >= 3}
            sorted_sectors = sorted(sector_avg.items(), key=lambda x: (-x[1], x[0]))
            if sorted_sectors:
                top_n = min(5, len(sorted_sectors))
                lines.append("\n昨日板块涨幅前5:")
                for s, c in sorted_sectors[:top_n]:
                    lines.append(f"  ▲ {s}: {c:+.2f}%")
                if len(sorted_sectors) > 5:
                    lines.append("昨日板块跌幅前5:")
                    for s, c in sorted_sectors[-min(5, len(sorted_sectors)) :]:
                        lines.append(f"  ▼ {s}: {c:+.2f}%")

        # P0: 持仓 + 自选股相关公告
        p0_announcements = ctx.tool_call_cache.get("_p0_announcements", [])
        if p0_announcements:
            masker = getattr(ctx, "date_masker", None)
            lines.append("\n=== P0 公告（持仓/自选股相关）===")
            for ann in p0_announcements[:10]:
                when = masker.mask_datetime(ann["time"]) if masker is not None else ann["time"][:10]
                lines.append(f"  [{ann['stock_code']}] {ann['title']} ({when})")

        # P1: 国家级政策快讯
        p1_policy = ctx.tool_call_cache.get("_p1_policy", [])
        if p1_policy:
            lines.append("\n=== P1 政策快讯 ===")
            for news in p1_policy[:5]:
                lines.append(f"  {news['content'][:100]}")

        # 自选股行情
        watchlist = ctx.tool_call_cache.get("watchlist", {})
        if watchlist:
            lines.append("\n自选股追踪:")
            for code, reason in watchlist.items():
                wl_str = f"  {code}"
                if reason:
                    wl_str += f" ({reason})"
                daily = ctx.preloaded_daily.get(code)
                if daily is not None and not daily.empty:
                    filtered = daily[daily["date"] < ctx.current_date]
                    if not filtered.empty:
                        last_close = float(filtered.iloc[-1]["close"])
                        wl_str += f" 最新{last_close:.2f}"
                        if len(filtered) >= 2:
                            prev_close = float(filtered.iloc[-2]["close"])
                            chg = (last_close - prev_close) / prev_close * 100
                            wl_str += f" {chg:+.2f}%"
                lines.append(wl_str)

        bus = ctx._bus
        if bus is not None and hasattr(bus, "list_conditional_orders"):
            active_conditions = bus.list_conditional_orders(status="active")
            if active_conditions:
                lines.append("\n环境托管的活动条件单:")
                for order in active_conditions:
                    symbol = "≤" if order["comparator"] == "price_lte" else "≥"
                    lines.append(
                        f"  [{order['order_id']}] {order['side']} {order['stock_code']} "
                        f"价格{symbol}{order['trigger_price']:.2f}，数量{order['quantity']}，"
                        f"状态={order['status']}"
                    )

        # 可用工具提示
        if available_tool_names is None:
            available_tool_names = [
                "get_kline",
                "get_stock_price",
                "get_stock_info",
                "get_market_overview",
                "screen_stocks",
                "get_sector_summary",
                "get_portfolio",
                "get_position",
                "get_fundamentals",
                "get_announcements",
                "get_news",
                "add_watchlist",
                "remove_watchlist",
                "execute_code",
            ]
        lines.append("\n可用工具: " + ", ".join(available_tool_names))

        brief = "\n".join(lines)
        date_masker = getattr(ctx, "date_masker", None)
        if date_masker is not None:
            brief = date_masker.mask_text(brief)
        entity_masker = getattr(ctx, "entity_masker", None)
        return entity_masker.mask_text(brief) if entity_masker is not None else brief

    @staticmethod
    def _format_window_news(ctx: ToolContext, window: str) -> str:
        """Format intra-day news for trading windows."""
        from datetime import datetime

        bus = ctx._bus
        news_mgr = getattr(bus, "_news_manager", None) if bus else None
        if news_mgr is None:
            return ""

        target_codes = set(ctx.portfolio.positions.keys())
        watchlist = ctx.tool_call_cache.get("watchlist", {})
        target_codes |= set(watchlist.keys())

        if window == "open":
            # 09:30 ~ 10:00
            start = datetime.combine(ctx.current_date, datetime.min.time()).replace(hour=9, minute=30)
            end = datetime.combine(ctx.current_date, datetime.min.time()).replace(hour=10, minute=0)
        else:
            # 10:00 ~ 14:30
            start = datetime.combine(ctx.current_date, datetime.min.time()).replace(hour=10, minute=0)
            end = datetime.combine(ctx.current_date, datetime.min.time()).replace(hour=14, minute=30)

        p0, p1 = news_mgr.get_window_news(target_codes, start, end)

        if not p0 and not p1:
            return ""

        lines = ["\n\n--- 盘中快讯 ---"]
        if p0:
            for ann in p0[:5]:
                lines.append(f"  [公告] {ann['stock_code']}: {ann['title']}")
        if p1:
            for news in p1[:3]:
                lines.append(f"  [政策] {news['content'][:80]}")

        text = "\n".join(lines)
        date_masker = getattr(ctx, "date_masker", None)
        if date_masker is not None:
            text = date_masker.mask_text(text)
        entity_masker = getattr(ctx, "entity_masker", None)
        return entity_masker.mask_text(text) if entity_masker is not None else text

    @staticmethod
    def _filter_window_bars(
        window_data: dict[str, pd.DataFrame], start_min: int, end_min: int
    ) -> dict[str, pd.DataFrame]:
        """Filter 5-min bars to a specific time range (in minutes since midnight)."""

        result = {}
        for code, df in window_data.items():
            if df.empty or "datetime" not in df.columns:
                continue
            minutes = df["datetime"].dt.hour * 60 + df["datetime"].dt.minute
            filtered = df[(minutes >= start_min) & (minutes <= end_min)]
            if not filtered.empty:
                result[code] = filtered
        return result

    @staticmethod
    def _format_window_klines(
        window_data: dict[str, pd.DataFrame],
        title: str,
        execution_prices: dict | None = None,
        ctx: ToolContext | None = None,
    ) -> str:
        """格式化窗口5分钟K线。下单以窗口最后一根bar收盘价成交。"""

        def mask(text: str) -> str:
            entity_masker = getattr(ctx, "entity_masker", None) if ctx is not None else None
            return entity_masker.mask_text(text) if entity_masker is not None else text

        if not window_data:
            if execution_prices:
                lines = [f"=== {title} ===", "", "当前无5分钟K线数据，但以下股票可交易："]
                for code, price in sorted(execution_prices.items())[:15]:
                    lines.append(f"  {code}: 成交价 {float(price):.2f}")
                return mask("\n".join(lines))
            return mask(
                f"=== {title} ===\n（当前自选/持仓尚无可见的5分钟窗口数据。你仍可对有当日5分钟数据的股票下单。）"
            )

        lines = [f"=== {title} ==="]
        lines.append("（下单成交价 = 本窗口最后一根5分钟bar收盘价）")
        for code, df in sorted(window_data.items()):
            if df.empty:
                continue
            lines.append(f"\n{code}:")
            lines.append("  开盘    最高    最低    收盘    成交量")
            for _, row in df.iterrows():
                lines.append(
                    f"  {float(row['open']):8.2f} {float(row['high']):7.2f} "
                    f"{float(row['low']):7.2f} {float(row['close']):7.2f} "
                    f"{safe_int(row.get('volume', 0)):>8}"
                )
        return mask("\n".join(lines))
