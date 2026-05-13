"""Tests for BacktestEngine (date progression + multi-agent scheduling)."""

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pytest

from finharness.core.engine import BacktestEngine, EngineConfig
from finharness.core.events import EventBus
from finharness.core.calendar import TradingCalendar
from finharness.core.market_profile import AShareProfile
from finharness.core.portfolio import Portfolio


@runtime_checkable
class AgentProtocol(Protocol):
    agent_id: str
    name: str

    async def on_day(self, env, current_date: date) -> None: ...


class DummyAgent:
    """Minimal agent that tracks which days it was called."""

    def __init__(self, agent_id: str = "dummy"):
        self.agent_id = agent_id
        self.name = "DummyAgent"
        self.days_called: list[date] = []

    async def on_day(self, env, current_date: date) -> None:
        self.days_called.append(current_date)


class BuyOnceAgent:
    """Agent that buys on first opportunity."""

    def __init__(self):
        self.agent_id = "buyer"
        self.name = "BuyOnceAgent"
        self._bought = False

    async def on_day(self, env, current_date: date) -> None:
        if not self._bought:
            await env.place_order(
                agent_id=self.agent_id,
                stock_code="600519",
                side="buy",
                quantity=100,
            )
            self._bought = True


class TestBacktestEngine:
    @pytest.mark.asyncio
    async def test_runs_through_trading_days(self):
        engine = self._make_engine()
        agent = DummyAgent()
        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
        )
        assert result.trading_days == 5
        assert len(agent.days_called) == 5

    @pytest.mark.asyncio
    async def test_skips_weekends(self):
        engine = self._make_engine()
        agent = DummyAgent()
        await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 8),  # Fri
            end_date=date(2024, 3, 11),   # Mon
        )
        # Fri + Mon only (skips Sat/Sun)
        assert len(agent.days_called) == 2

    @pytest.mark.asyncio
    async def test_multiple_agents(self):
        engine = self._make_engine()
        a1 = DummyAgent("a1")
        a2 = DummyAgent("a2")
        await engine.run(
            agents=[a1, a2],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
        )
        assert len(a1.days_called) == 2
        assert len(a2.days_called) == 2

    @pytest.mark.asyncio
    async def test_emits_events(self):
        bus = EventBus()
        events_received = []
        bus.on("day_start", lambda **kw: events_received.append(("day_start", kw)))
        bus.on("day_end", lambda **kw: events_received.append(("day_end", kw)))
        bus.on("run_start", lambda **kw: events_received.append(("run_start", kw)))
        bus.on("run_end", lambda **kw: events_received.append(("run_end", kw)))

        engine = self._make_engine(event_bus=bus)
        agent = DummyAgent()
        await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
        )
        event_types = [e[0] for e in events_received]
        assert "run_start" in event_types
        assert "run_end" in event_types
        assert "day_start" in event_types
        assert "day_end" in event_types

    @pytest.mark.asyncio
    async def test_breakpoints(self):
        engine = self._make_engine()
        agent = DummyAgent()
        breakpoint_dates: list[date] = []

        bus = EventBus()
        bus.on("breakpoint_hit", lambda **kw: breakpoint_dates.append(kw.get("date")))
        engine._event_bus = bus

        await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
            breakpoints=[date(2024, 3, 6)],
        )
        assert date(2024, 3, 6) in breakpoint_dates

    @pytest.mark.asyncio
    async def test_result_contains_agent_equity(self):
        engine = self._make_engine()
        agent = DummyAgent()
        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
        )
        assert agent.agent_id in result.agent_data
        assert "equity_curve" in result.agent_data[agent.agent_id]

    def _make_engine(self, event_bus: EventBus | None = None) -> BacktestEngine:
        config = EngineConfig(
            initial_cash=Decimal("1000000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
        )
        return BacktestEngine(
            config=config,
            market_data=self._dummy_market_data(),
            event_bus=event_bus or EventBus(),
        )

    @staticmethod
    def _dummy_market_data():
        """Returns a minimal market data provider for testing."""
        from finharness.core.engine import MarketDataProvider

        class DummyData(MarketDataProvider):
            def get_price(self, stock_code: str, trade_date: date) -> Decimal | None:
                return Decimal("1800.00")

            def get_prev_close(self, stock_code: str, trade_date: date) -> Decimal | None:
                return Decimal("1750.00")

        return DummyData()
