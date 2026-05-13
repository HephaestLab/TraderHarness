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
        self._registry.register(FINISH_DAY)

        self._memory = DailyMemory(agent_id=agent_id, storage_dir=memory_dir)

        self._loop = AgentLoop(
            llm_client=llm_client,
            tool_registry=self._registry,
            system_prompt=self._system_prompt,
            memory=self._memory,
        )

        self.day_results: list[DayResult] = []

    async def on_day(self, bus, current_date: date) -> None:
        """TradingBus 模式：总线通知新交易日。"""
        from finharness.core.portfolio import Portfolio

        portfolio = bus._portfolio

        initial = portfolio.cash + sum(
            p.avg_cost * p.quantity for p in portfolio.positions.values()
        )

        # 获取所有持仓+种子股的执行价
        codes = set(portfolio.positions.keys())
        open_prices = {}
        for code in codes:
            op = await bus.get_execution_price(code, "open")
            if op:
                open_prices[code] = op

        ctx = ToolContext(
            current_date=current_date,
            current_phase="pre_market",
            portfolio=portfolio,
            initial_cash=initial,
            preloaded_daily={},
            execution_price=open_prices,
            workspace_root=self.agent_id,
            max_position_pct=self.max_position_pct,
            max_positions=self.max_positions,
            _bus=bus,
        )

        result = await self._loop.run_day(current_date, ctx)
        self.day_results.append(result)
