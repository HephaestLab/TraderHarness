"""TradingEnv — main entry point for backtesting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from finharness.core.calendar import TradingCalendar
from finharness.core.engine import BacktestEngine, EngineConfig, EngineResult, MarketDataProvider
from finharness.core.events import EventBus
from finharness.core.market_profile import AShareProfile


@dataclass
class EnvConfig:
    start_date: date = date(2024, 1, 2)
    end_date: date = date(2024, 12, 31)
    initial_cash: Decimal = Decimal("1000000")
    warmup_days: int = 0


class _DefaultMarketData:
    """Placeholder market data that returns None (no data)."""

    def get_price(self, stock_code: str, trade_date: date) -> Decimal | None:
        return None

    def get_prev_close(self, stock_code: str, trade_date: date) -> Decimal | None:
        return None


class TradingEnv:
    """Top-level environment wrapping the backtest engine.

    Provides both sync (run) and async (run_async) interfaces.
    """

    def __init__(
        self,
        config: EnvConfig | None = None,
        market_data: Any | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config or EnvConfig()
        self._market_data = market_data or _DefaultMarketData()
        self._event_bus = event_bus or EventBus()

    def run(self, agents: Any, breakpoints: list[date] | None = None) -> EngineResult:
        """Synchronous entry point."""
        return asyncio.run(self.run_async(agents, breakpoints))

    async def run_async(
        self, agents: Any, breakpoints: list[date] | None = None
    ) -> EngineResult:
        """Asynchronous entry point for advanced users."""
        if not isinstance(agents, list):
            agents = [agents]

        engine_config = EngineConfig(
            initial_cash=self._config.initial_cash,
            profile=AShareProfile(),
            calendar=TradingCalendar(),
        )
        engine = BacktestEngine(
            config=engine_config,
            market_data=self._market_data,
            event_bus=self._event_bus,
        )

        return await engine.run(
            agents=agents,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            breakpoints=breakpoints,
        )
