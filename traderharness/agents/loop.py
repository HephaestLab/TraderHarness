"""Agent Loop — 核心三阶段 agentic 循环。

每个交易日：盘前分析 → 开盘窗口 → 尾盘窗口 → finish_day。
直接从源项目 backend/agents/agentic/agent_loop.py 迁移。
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from traderharness.agents.context import ContextManager
from traderharness.agents.llm_client import LLMClient
from traderharness.agents.memory import DailyMemory
from traderharness.tools._coerce import safe_int
from traderharness.tools.registry import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from traderharness.core.budget import TokenBudget
    from traderharness.core.events import EventBus
    from traderharness.trajectory.collector import TrajectoryCollector

MAX_TOOL_RESULT_CHARS = 3000


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


def _serialize_tool_result(result: dict) -> str:
    """Serialize tool result, truncating if over budget."""
    text = json.dumps(_json_safe(result), ensure_ascii=False, allow_nan=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        return text[:MAX_TOOL_RESULT_CHARS] + "... (truncated)"
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

    async def run_day(self, current_date: date, ctx: ToolContext) -> DayResult:
        """执行一个完整交易日的三阶段循环。"""
        self._context.reset()
        self._total_tokens = 0

        if self.trajectory:
            self.trajectory.start_day(current_date, {"cash": float(ctx.portfolio.cash)})

        self._context.add_message({"role": "system", "content": self.system_prompt})

        if self.memory:
            memory_text = self.memory.to_prompt_text(
                before_date=current_date,
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
        morning_brief = self._build_morning_brief(ctx)

        # Record morning brief in trajectory
        if self.trajectory:
            self.trajectory.record_step(current_date, "morning_brief", {"content": morning_brief})
        remaining_info = ""
        if self.remaining_trading_days is not None and self.total_trading_days is not None:
            day_num = self.total_trading_days - self.remaining_trading_days
            remaining_info = (
                f"\n回测进度: 第{day_num}天/{self.total_trading_days}天"
                f"（剩余{self.remaining_trading_days}个交易日）"
            )
        self._context.add_message(
            {
                "role": "user",
                "content": f"新的交易日开始。{remaining_info}\n\n{morning_brief}\n\n"
                f"现在是盘前分析阶段，你可以使用工具研究市场，但不能下单。",
            }
        )
        await self._run_phase(ctx, max_iter=self.max_pre_iterations, exclude_tools={"place_order"})

        # === Phase 2: 开盘窗口 (分两轮推进) ===
        await self._context.compress()

        from traderharness.agents.window_context import refresh_trading_window

        # Rebuild focus set after pre-market watchlist mutations.
        refresh_trading_window(ctx, window="open")

        ctx.current_phase = "open_window"
        ctx._current_sub_window = "open_1"
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
        window_text = self._format_window_klines(
            half1, "开盘窗口 前半 (9:30-9:50)", ctx.execution_price, ctx
        )
        window_news = self._format_window_news(ctx, "open")
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}{window_news}\n\n你现在可以下单"
                    "（成交价=当前最新bar收盘价），或等待看后续走势。"
                ),
            }
        )
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # Round 2: 9:50-10:00 (后3根bar)
        ctx._current_sub_window = "open_2"
        half2 = self._filter_window_bars(ctx.window_minutes, 9 * 60 + 55, 10 * 60)
        window_text = self._format_window_klines(
            half2, "开盘窗口 后半 (9:50-10:00)", ctx.execution_price, ctx
        )
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}\n\n开盘窗口即将结束。下单则以10:00价格成交，不下单则等尾盘。"
                ),
            }
        )
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # Compress open window phase before close
        await self._context.compress()

        # === Phase 3: 尾盘窗口 (分两轮推进) ===
        # Include same-day buys and watchlist adds that happened in the open window.
        refresh_trading_window(ctx, window="close")

        ctx.current_phase = "close_window"
        ctx._current_sub_window = "close_1"
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
        window_text = self._format_window_klines(
            half1, "尾盘窗口 前半 (14:30-14:50)", ctx.execution_price, ctx
        )
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}{window_news}\n\n你可以下单"
                    "（成交价=当前最新bar收盘价），或等待看尾盘走势。"
                ),
            }
        )
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # Round 2: 14:50-15:00 (后3根bar)
        ctx._current_sub_window = "close_2"
        half2 = self._filter_window_bars(ctx.window_minutes, 14 * 60 + 55, 15 * 60)
        window_text = self._format_window_klines(
            half2, "尾盘窗口 后半 (14:50-15:00)", ctx.execution_price, ctx
        )
        self._context.add_message(
            {
                "role": "user",
                "content": (
                    f"{window_text}\n\n收盘在即。下单则以收盘价成交。"
                    "操作完成后请调用 finish_day 总结今天。"
                ),
            }
        )
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # 确保 finish_day 被调用
        if "finish_day_summary" in ctx.tool_call_cache:
            summary = ctx.tool_call_cache["finish_day_summary"]
        else:
            summary = await self._ensure_finish(ctx)

        # 保存记忆
        if self.memory:
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

    async def _run_phase(
        self,
        ctx: ToolContext,
        max_iter: int,
        exclude_tools: set[str],
    ) -> None:
        """单阶段的 tool-use loop。"""
        tools_schema = self.registry.get_openai_tools_schema(exclude=exclude_tools)
        consecutive_errors = 0

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

        for _ in range(max_iter):
            if self._budget and self._budget.is_exhausted:
                logger.warning("Token budget exhausted, stopping phase")
                return

            if self._context.needs_compression():
                await self._context.compress()

            request_messages = self._context.get_api_messages()
            response = await self.llm_client.chat(
                messages=request_messages,
                tools=tools_schema,
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
                        response["content"] = entity_masker.sanitize_agent_text(
                            response["content"]
                        )
                if response.get("reasoning_content"):
                    if date_masker is not None:
                        response["reasoning_content"] = date_masker.mask_text(
                            response["reasoning_content"]
                        )
                    if entity_masker is not None:
                        response["reasoning_content"] = entity_masker.sanitize_agent_text(
                            response["reasoning_content"]
                        )
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
                            parsed_arguments = entity_masker.sanitize_agent_obj(
                                parsed_arguments
                            )
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
            self._emit(
                "llm_response",
                date=ctx.current_date,
                agent_id=getattr(ctx, "agent_id", ""),
                phase=ctx.current_phase,
                has_tool_calls=bool(response.get("tool_calls")),
                tokens=response.get("_usage", {}).get("total_tokens", 0),
            )

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
                break

            should_finish = False
            # Partition: the historical read-then-write message order is part of
            # the replay fingerprint. Keep that ordering, but execute each batch
            # serially (concurrent gather previously raced on shared frames).
            read_only_tools = {
                "get_kline",
                "get_stock_price",
                "get_stock_info",
                "get_market_overview",
                "get_sector_summary",
                "get_portfolio",
                "get_position",
                "get_fundamentals",
                "get_business_segments",
                "get_valuation",
                "get_announcements",
                "get_news",
                "get_watchlist",
            }

            parsed_calls = []
            for tc in response["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    self._context.add_message(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(
                                {"error": "参数解析失败，请检查JSON格式"}, ensure_ascii=False
                            ),
                        }
                    )
                    consecutive_errors += 1
                    continue
                parsed_calls.append((tc, tool_name, arguments))

            read_batch = [
                (tc, name, args) for tc, name, args in parsed_calls if name in read_only_tools
            ]
            write_batch = [
                (tc, name, args) for tc, name, args in parsed_calls if name not in read_only_tools
            ]

            async def _run_tool(tc, tool_name, arguments, *, read_only: bool) -> None:
                nonlocal consecutive_errors, should_finish
                if tool_name == "finish_day":
                    should_finish = True
                    ctx.tool_call_cache["finish_day_summary"] = arguments.get("summary", "")

                result = await self.registry.execute(tool_name, arguments, ctx)
                self._emit(
                    "tool_call",
                    date=ctx.current_date,
                    agent_id=getattr(ctx, "agent_id", ""),
                    tool=tool_name,
                    args=arguments,
                    success="error" not in result,
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
                    _serialize_tool_result(result)
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
                if "error" in result:
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0

            for tc, name, args in read_batch:
                await _run_tool(tc, name, args, read_only=True)
            for tc, name, args in write_batch:
                await _run_tool(tc, name, args, read_only=False)

            if should_finish or consecutive_errors >= 3:
                return

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

        tools_schema = [finish_tool.to_openai_schema()]
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

    @staticmethod
    def _build_morning_brief(ctx: ToolContext) -> str:
        """从已有数据生成晨报。包含持仓涨跌、总收益率、板块概览、P0公告、P1政策。"""
        lines = ["=== 市场晨报 ==="]

        # 总资产与收益率 — 盘前只能用昨收，禁止用当日开盘窗成交价（防前视）。
        from traderharness.agents.window_context import previous_close_prices

        prices = previous_close_prices(ctx)
        total_value = (
            float(ctx.portfolio.total_value(prices)) if prices else float(ctx.portfolio.cash)
        )
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
                    f"  {code}: {pos.quantity}股, 成本{float(pos.avg_cost):.2f}"
                    f"{change_str}{pnl_str}{suspend_str}"
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
            lines.append(
                f"\n昨日全市场({total_up + total_down}只): 上涨{total_up} 下跌{total_down}"
            )
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

        # 可用工具提示
        lines.append(
            "\n可用工具: get_kline(K线), get_stock_price(最新价), get_stock_info(基本面), "
            "get_market_overview(全市场概览), screen_stocks(选股), get_sector_summary(板块), "
            "get_portfolio(持仓), get_position(个股持仓), "
            "get_fundamentals(财务指标), get_announcements(公告), get_news(快讯), "
            "add_watchlist/remove_watchlist(自选股), "
            "execute_code(Python沙箱, 工作目录文件可直接读写)"
        )

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
            start = datetime.combine(ctx.current_date, datetime.min.time()).replace(
                hour=9, minute=30
            )
            end = datetime.combine(ctx.current_date, datetime.min.time()).replace(hour=10, minute=0)
        else:
            # 10:00 ~ 14:30
            start = datetime.combine(ctx.current_date, datetime.min.time()).replace(
                hour=10, minute=0
            )
            end = datetime.combine(ctx.current_date, datetime.min.time()).replace(
                hour=14, minute=30
            )

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
                f"=== {title} ===\n"
                "（当前自选/持仓尚无可见的5分钟窗口数据。"
                "你仍可对有当日5分钟数据的股票下单。）"
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
