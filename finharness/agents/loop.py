"""Agent Loop — 核心三阶段 agentic 循环。

每个交易日：盘前分析 → 开盘窗口 → 尾盘窗口 → finish_day。
直接从源项目 backend/agents/agentic/agent_loop.py 迁移。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pandas as pd

from finharness.tools.registry import ToolRegistry, ToolContext
from finharness.agents.memory import DailyMemory
from finharness.agents.context import ContextManager
from finharness.agents.llm_client import LLMClient

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
    ) -> None:
        self.llm_client = llm_client
        self.registry = tool_registry
        self.system_prompt = system_prompt
        self.memory = memory
        self.max_pre_iterations = max_pre_iterations
        self.max_window_iterations = max_window_iterations
        self._context = ContextManager(max_context_tokens=60000)
        self._total_tokens: int = 0
        self.remaining_trading_days: int | None = None
        self.total_trading_days: int | None = None

    async def run_day(self, current_date: date, ctx: ToolContext) -> DayResult:
        """执行一个完整交易日的三阶段循环。"""
        self._context.reset()
        self._total_tokens = 0

        self._context.add_message({"role": "system", "content": self.system_prompt})

        if self.memory:
            memory_text = self.memory.to_prompt_text(before_date=current_date)
            if memory_text:
                self._context.add_message({"role": "system", "content": memory_text})

        # === Phase 1: 盘前分析 ===
        ctx.current_phase = "pre_market"
        morning_brief = self._build_morning_brief(ctx)
        remaining_info = ""
        if self.remaining_trading_days is not None:
            remaining_info = f"\n回测进度: 第{self.total_trading_days - self.remaining_trading_days}天/{self.total_trading_days}天（剩余{self.remaining_trading_days}个交易日）"
        self._context.add_message({
            "role": "user",
            "content": f"今天是 {current_date}，新的交易日开始。{remaining_info}\n\n{morning_brief}\n\n"
                       f"现在是盘前分析阶段，你可以使用工具研究市场，但不能下单。",
        })
        await self._run_phase(ctx, max_iter=self.max_pre_iterations, exclude_tools={"place_order"})

        # === Phase 2: 开盘窗口 ===
        ctx.current_phase = "open_window"
        window_text = self._format_window_klines(ctx.window_minutes, "开盘窗口 (9:30-10:00)", ctx.execution_price)
        self._context.add_message({
            "role": "user",
            "content": f"{window_text}\n\n你现在可以下单。如果不想交易，直接回复你的观察即可。",
        })
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # === Phase 3: 尾盘窗口 ===
        ctx.current_phase = "close_window"
        if ctx.close_prices:
            ctx.execution_price = ctx.close_prices
        elif ctx._bus is not None:
            close_prices = {}
            for code in list(ctx.execution_price.keys()) + list(ctx.portfolio.positions.keys()):
                cp = ctx._bus.get_execution_price(code, "close")
                if cp:
                    close_prices[code] = cp
            if close_prices:
                ctx.execution_price = close_prices

        window_text = self._format_window_klines(ctx.window_minutes, "尾盘窗口 (14:30-15:00)", ctx.execution_price)
        self._context.add_message({
            "role": "user",
            "content": f"{window_text}\n\n尾盘窗口结束，收盘价即为成交价。你可以决定是否加仓/减仓/平仓。"
                       f"\n操作完成后请调用 finish_day 总结今天。",
        })
        await self._run_phase(ctx, max_iter=self.max_window_iterations, exclude_tools=set())

        # 确保 finish_day 被调用
        if "finish_day_summary" in ctx.tool_call_cache:
            summary = ctx.tool_call_cache["finish_day_summary"]
        else:
            summary = await self._ensure_finish(ctx)

        # 保存记忆
        if self.memory:
            self.memory.add(
                current_date, summary,
                trades=ctx.trade_results,
            )

        return DayResult(
            trades=ctx.trade_results,
            summary=summary,
            iterations=self._total_tokens,
        )

    async def _run_phase(
        self,
        ctx: ToolContext,
        max_iter: int,
        exclude_tools: set[str],
    ) -> None:
        """单阶段的 tool-use loop。"""
        tools_schema = self.registry.get_openai_tools_schema(exclude=exclude_tools)
        consecutive_errors = 0

        for _ in range(max_iter):
            if self._context.needs_compression():
                await self._context.compress()

            response = await self.llm_client.chat(
                messages=self._context.get_api_messages(),
                tools=tools_schema,
            )

            assistant_dict = {"role": "assistant", "content": response.get("content", "") or ""}
            if response.get("tool_calls"):
                assistant_dict["tool_calls"] = response["tool_calls"]
            self._context.add_message(assistant_dict)

            usage = response.get("_usage", {})
            if usage:
                self._total_tokens += usage.get("total_tokens", 0)

            if not response.get("tool_calls"):
                break

            should_finish = False
            for tc in response["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    self._context.add_message({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"error": "参数解析失败，请检查JSON格式"}, ensure_ascii=False),
                    })
                    consecutive_errors += 1
                    continue

                if tool_name == "finish_day":
                    should_finish = True
                    ctx.tool_call_cache["finish_day_summary"] = arguments.get("summary", "")

                result = await self.registry.execute(tool_name, arguments, ctx)
                self._context.add_message({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

                if "error" in result:
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0

            if should_finish or consecutive_errors >= 3:
                return

    async def _ensure_finish(self, ctx: ToolContext) -> str:
        """确保 Agent 调用了 finish_day。"""
        self._context.add_message({
            "role": "user",
            "content": "收盘了。请调用 finish_day 写下今天的总结。",
        })

        finish_tool = self.registry.get_tool("finish_day")
        if finish_tool is None:
            return "（无 finish_day 工具）"

        tools_schema = [finish_tool.to_openai_schema()]
        response = await self.llm_client.chat(
            messages=self._context.get_api_messages(),
            tools=tools_schema,
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

        return summary or "（Agent 未提供当日总结）"

    @staticmethod
    def _build_morning_brief(ctx: ToolContext) -> str:
        """从已有数据生成晨报。包含持仓涨跌、总收益率、板块概览。"""
        lines = ["=== 市场晨报 ==="]

        # 总资产与收益率
        prices = ctx.execution_price if ctx.execution_price else {}
        total_value = float(ctx.portfolio.total_value(prices)) if prices else float(ctx.portfolio.cash)
        initial = float(ctx.initial_cash)
        return_pct = ((total_value - initial) / initial * 100) if initial > 0 else 0.0
        lines.append(f"\n总资产: {total_value:,.0f}元 | 累计收益: {return_pct:+.2f}%")

        # 持仓概况 + 昨日涨跌 + 浮盈
        positions = ctx.portfolio.positions
        cash = float(ctx.portfolio.cash)
        if positions:
            lines.append(f"持仓: {len(positions)}只 | 可用资金: {cash:,.0f}元")
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
                lines.append(f"  {code}: {pos.quantity}股, 成本{float(pos.avg_cost):.2f}{change_str}{pnl_str}")
        else:
            lines.append(f"\n当前空仓 | 可用资金: {cash:,.0f}元")

        # 板块涨跌概览（按行业聚合）— 优化：用 bisect 避免 DataFrame boolean indexing
        import bisect
        from finharness.data.stock_registry_loader import get_stock_industry
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
            sorted_sectors = sorted(sector_avg.items(), key=lambda x: -x[1])
            if sorted_sectors:
                top_n = min(5, len(sorted_sectors))
                lines.append("\n昨日板块涨幅前5:")
                for s, c in sorted_sectors[:top_n]:
                    lines.append(f"  ▲ {s}: {c:+.2f}%")
                if len(sorted_sectors) > 5:
                    lines.append("昨日板块跌幅前5:")
                    for s, c in sorted_sectors[-min(5, len(sorted_sectors)):]:
                        lines.append(f"  ▼ {s}: {c:+.2f}%")

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
        lines.append("\n可用工具: get_kline(K线), get_stock_price(最新价), get_stock_info(基本面), "
                     "screen_stocks(选股), get_market_overview(大盘), "
                     "get_portfolio(持仓), get_position(个股持仓), "
                     "add_watchlist/remove_watchlist(自选股), "
                     "read_file/write_file(笔记), run_script(执行脚本)")

        return "\n".join(lines)

    @staticmethod
    def _format_window_klines(window_data: dict[str, pd.DataFrame], title: str, execution_prices: dict | None = None) -> str:
        """格式化窗口数据。"""
        if not window_data:
            if execution_prices:
                lines = [f"=== {title} ===", "", "当前无5分钟K线数据，但以下股票可交易："]
                for code, price in list(execution_prices.items())[:15]:
                    lines.append(f"  {code}: 成交价 {float(price):.2f}")
                lines.append("")
                lines.append("你可以使用 place_order 下单，成交价如上所示。")
                return "\n".join(lines)
            return f"=== {title} ===\n（当天无行情数据，无法交易）"

        lines = [f"=== {title} ==="]
        for code, df in window_data.items():
            if df.empty:
                continue
            lines.append(f"\n{code}:")
            lines.append("  时间        开盘    最高    最低    收盘    成交量")
            for _, row in df.iterrows():
                time_str = str(row.get("datetime", row.get("date", "")))[-5:]
                lines.append(
                    f"  {time_str}  {float(row['open']):8.2f} {float(row['high']):7.2f} "
                    f"{float(row['low']):7.2f} {float(row['close']):7.2f} {int(row.get('volume', 0)):>8}"
                )
        return "\n".join(lines)
