"""TradingEnv — main entry point for backtesting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from traderharness.core.calendar import TradingCalendar
from traderharness.core.engine import BacktestEngine, EngineConfig, EngineResult
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile


@dataclass
class EnvConfig:
    start_date: date = date(2024, 1, 2)
    end_date: date = date(2024, 12, 31)
    initial_cash: Decimal = Decimal("1000000")
    warmup_days: int = 0


class TradingEnv:
    """Top-level environment wrapping the backtest engine.

    Provides both sync (run) and async (run_async) interfaces.
    """

    def __init__(
        self,
        config: EnvConfig | None = None,
        data_provider: Any | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config or EnvConfig()
        self._data_provider = data_provider
        self._event_bus = event_bus or EventBus()

    def run(self, agents: Any, breakpoints: list[date] | None = None) -> EngineResult:
        """Synchronous entry point."""
        return asyncio.run(self.run_async(agents, breakpoints))

    async def run_async(self, agents: Any, breakpoints: list[date] | None = None) -> EngineResult:
        """Asynchronous entry point."""
        if not isinstance(agents, list):
            agents = [agents]

        engine_config = EngineConfig(
            initial_cash=self._config.initial_cash,
            profile=AShareProfile(),
            calendar=TradingCalendar(),
        )
        engine = BacktestEngine(
            config=engine_config,
            data_provider=self._data_provider,
            event_bus=self._event_bus,
        )

        return await engine.run(
            agents=agents,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            breakpoints=breakpoints,
            warmup_days=self._config.warmup_days,
        )
