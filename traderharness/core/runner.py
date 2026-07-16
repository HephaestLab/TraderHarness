"""Backtest runner — launches backtest in a background thread with live event feed.

Usage from Streamlit:
    from traderharness.core.runner import BacktestRunner

    runner = BacktestRunner(config)
    runner.start()

    # In render loop:
    for event in runner.feed:
        st.write(event)
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from traderharness.core.engine import BacktestEngine, EngineConfig, EngineResult
from traderharness.core.live_feed import LiveFeed


@dataclass
class RunConfig:
    start_date: date
    end_date: date
    initial_cash: float = 1_000_000
    agents: list[dict[str, Any]] | None = None


class BacktestRunner:
    """Wraps BacktestEngine in a background thread with LiveFeed for UI consumption."""

    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._feed = LiveFeed()
        self._thread: threading.Thread | None = None
        self._result: EngineResult | None = None
        self._error: Exception | None = None

    @property
    def feed(self) -> LiveFeed:
        return self._feed

    @property
    def result(self) -> EngineResult | None:
        return self._result

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._result = asyncio.run(self._async_run())
        except Exception as e:
            self._error = e
            self._feed.push("error", message=str(e))
        finally:
            if not self._feed.done:
                self._feed.push("run_end", trading_days=0)

    async def _async_run(self) -> EngineResult:
        engine_config = EngineConfig(
            initial_cash=Decimal(str(self._config.initial_cash)),
        )
        engine = BacktestEngine(config=engine_config, event_bus=self._feed.event_bus)

        agents = self._build_agents()
        self._feed.push("loading_data", message="Loading market data...")

        result = await engine.run(
            agents=agents,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
        )
        return result

    def _build_agents(self) -> list:
        from traderharness.agents.tool_agent import ToolAgent
        from traderharness.agents.llm_client import LLMClient

        agent_configs = self._config.agents or [{"id": "default", "name": "Default Agent"}]
        agents = []

        for cfg in agent_configs:
            llm_client = LLMClient(model=cfg.get("model", None))
            agent = ToolAgent(
                agent_id=cfg.get("id", "agent_0"),
                name=cfg.get("name", "Agent"),
                llm_client=llm_client,
                persona=cfg.get("persona", "你是一位经验丰富的主观交易员。"),
                initial_cash=Decimal(str(self._config.initial_cash)),
                max_positions=cfg.get("max_positions", 4),
                max_position_pct=cfg.get("max_position_pct", 25.0),
                event_bus=self._feed.event_bus,
            )
            agents.append(agent)

        return agents
