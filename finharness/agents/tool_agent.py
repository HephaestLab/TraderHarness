"""ToolAgent — 完整的 Tool-Use Agentic Agent。

从源项目 backend/agents/agentic/tool_agent.py 迁移。
支持 TradingBus 模式：通过 on_day() 接入总线，Agent 自主查询一切数据。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pandas as pd

from finharness.agents.loop import AgentLoop, DayResult
from finharness.agents.memory import DailyMemory
from finharness.agents.llm_client import LLMClient
from finharness.tools.registry import ToolRegistry, ToolContext
from finharness.tools.market import GET_KLINE, GET_STOCK_PRICE, GET_STOCK_INFO
from finharness.tools.portfolio import GET_PORTFOLIO, GET_POSITION
from finharness.tools.trading import PLACE_ORDER
from finharness.tools.control import FINISH_DAY
from finharness.tools.analysis import GET_MARKET_OVERVIEW, SCREEN_STOCKS, GET_SECTOR_SUMMARY
from finharness.tools.filesystem import READ_FILE, WRITE_FILE, LIST_FILES
from finharness.tools.scripting import RUN_SCRIPT
from finharness.tools.watchlist import ADD_WATCHLIST, REMOVE_WATCHLIST, GET_WATCHLIST

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是一位A股交易员，正在模拟交易环境中回测对战。初始资金{initial_cash}元。

## 每天流程

**盘前分析**：你会收到市场晨报。可以自由使用工具研究市场，但不能下单。
**开盘窗口 (9:30-10:00)**：可以下单，成交价为开盘价。
**尾盘窗口 (14:30-15:00)**：可以下单，成交价为收盘价。
完成后调用 finish_day 写下今日总结。

## 交易规则

1. T+1：今天买入的股票明天才能卖
2. 同一只股票一天只能操作一次
3. 买入数量必须是100的整数倍
4. 涨跌停：主板±10%，创业板/科创板±20%
5. 你不知道未来会发生什么，只能基于已有数据判断

## 风控约束

- 单只股票仓位不超过总资产的{max_position_pct}%
- 最多同时持有{max_positions}只股票
- 空仓也是策略，不必强制交易

## 你的交易风格

{persona}
"""


class ToolAgent:
    """Tool-Use Agentic Agent — 通过 function calling 自主研究和交易。"""

    def __init__(
        self,
        agent_id: str,
        name: str,
        llm_client: LLMClient,
        persona: str = "你是一位经验丰富的主观交易员。",
        initial_cash: Decimal = Decimal("1000000"),
        max_positions: int = 4,
        max_position_pct: float = 25.0,
        memory_dir: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.llm_client = llm_client
        self.persona = persona
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct

        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            initial_cash=f"{float(initial_cash):,.0f}",
            max_position_pct=f"{max_position_pct:.0f}",
            max_positions=max_positions,
            persona=persona,
        )

        self._registry = ToolRegistry()
        self._registry.register(GET_KLINE)
        self._registry.register(GET_STOCK_PRICE)
        self._registry.register(GET_STOCK_INFO)
        self._registry.register(GET_MARKET_OVERVIEW)
        self._registry.register(SCREEN_STOCKS)
        self._registry.register(GET_SECTOR_SUMMARY)
        self._registry.register(GET_PORTFOLIO)
        self._registry.register(GET_POSITION)
        self._registry.register(PLACE_ORDER)
        self._registry.register(READ_FILE)
        self._registry.register(WRITE_FILE)
        self._registry.register(LIST_FILES)
        self._registry.register(RUN_SCRIPT)
        self._registry.register(ADD_WATCHLIST)
        self._registry.register(REMOVE_WATCHLIST)
        self._registry.register(GET_WATCHLIST)
        self._registry.register(FINISH_DAY)

        self._memory = DailyMemory(agent_id=agent_id, storage_dir=memory_dir)

        self._loop = AgentLoop(
            llm_client=llm_client,
            tool_registry=self._registry,
            system_prompt=self._system_prompt,
            memory=self._memory,
        )

        # 种子股票池：代表性蓝筹（确保每天晨报有数据）
        self._seed_codes = {"600519", "000001", "300750", "000858", "601318"}
        # 自选股（Agent 通过 add_watchlist 工具动态管理，跨天持久）
        self._watchlist_codes: set[str] = set()

        self.day_results: list[DayResult] = []

    async def on_day(self, bus, current_date: date) -> None:
        """TradingBus 模式：总线通知新交易日。"""
        from finharness.core.portfolio import Portfolio

        portfolio = bus._portfolio

        initial = portfolio.cash + sum(
            p.avg_cost * p.quantity for p in portfolio.positions.values()
        )

        # 预加载：持仓股 + 种子股 + 自选股
        preload_codes = set(portfolio.positions.keys())
        preload_codes.update(self._seed_codes)
        watchlist = self._loop._context.messages  # 从上一天的 tool_call_cache 获取自选股
        # 自选股持久化在 agent 级别
        preload_codes.update(self._watchlist_codes)
        preloaded_daily = {}
        for code in preload_codes:
            bars = await bus.get_daily_bars(code, days=120)
            if bars is not None and not bars.empty:
                preloaded_daily[code] = bars

        # 全市场采样：从 data provider 随机取 50 只用于板块概览
        all_stocks = await bus._data.get_stock_list() if bus._data else []
        import random
        sample_codes = [s["code"] for s in all_stocks if s["code"] not in preload_codes]
        random.shuffle(sample_codes)
        for code in sample_codes[:50]:
            bars = await bus.get_daily_bars(code, days=5)
            if bars is not None and not bars.empty:
                preloaded_daily[code] = bars

        # 获取执行价
        open_prices = {}
        for code in preload_codes:
            op = await bus.get_execution_price(code, "open")
            if op:
                open_prices[code] = op

        # 收盘价（尾盘窗口用）
        close_prices = {}
        for code in preload_codes:
            cp = await bus.get_execution_price(code, "close")
            if cp:
                close_prices[code] = cp

        ctx = ToolContext(
            current_date=current_date,
            current_phase="pre_market",
            portfolio=portfolio,
            initial_cash=initial,
            preloaded_daily=preloaded_daily,
            execution_price=open_prices,
            close_prices=close_prices,
            workspace_root=self.agent_id,
            max_position_pct=self.max_position_pct,
            max_positions=self.max_positions,
            _bus=bus,
        )

        # 传递回测进度
        if hasattr(bus, '_day_index') and hasattr(bus, '_total_days'):
            self._loop.remaining_trading_days = bus._total_days - bus._day_index - 1
            self._loop.total_trading_days = bus._total_days

        result = await self._loop.run_day(current_date, ctx)
        self.day_results.append(result)

        # 持久化自选股到 agent 级别（跨天保持）
        watchlist_from_ctx = ctx.tool_call_cache.get("watchlist", {})
        if watchlist_from_ctx:
            self._watchlist_codes = set(watchlist_from_ctx.keys())
