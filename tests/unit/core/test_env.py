"""Tests for TradingEnv — main entry point."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.core.env import TradingEnv, EnvConfig


class DummyAgent:
    def __init__(self, agent_id: str = "test"):
        self.agent_id = agent_id
        self.name = "TestAgent"
        self.days_called: list[date] = []

    async def on_day(self, env, current_date: date) -> None:
        self.days_called.append(current_date)


class TestTradingEnv:
    def test_sync_run(self):
        """env.run() is the sync wrapper."""
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 8),
                initial_cash=Decimal("1000000"),
            ),
        )
        agent = DummyAgent()
        result = env.run(agent)
        assert result.trading_days == 5
        assert len(agent.days_called) == 5

    def test_multiple_agents(self):
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 5),
                initial_cash=Decimal("1000000"),
            ),
        )
        a1 = DummyAgent("a1")
        a2 = DummyAgent("a2")
        result = env.run([a1, a2])
        assert len(a1.days_called) == 2
        assert len(a2.days_called) == 2

    @pytest.mark.asyncio
    async def test_async_run(self):
        """env.run_async() for advanced users."""
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 6),
                initial_cash=Decimal("1000000"),
            ),
        )
        agent = DummyAgent()
        result = await env.run_async(agent)
        assert result.trading_days == 3

    def test_result_has_metrics_placeholder(self):
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 5),
                initial_cash=Decimal("1000000"),
            ),
        )
        agent = DummyAgent()
        result = env.run(agent)
        assert hasattr(result, "agent_data")

    def test_custom_event_bus(self):
        from finharness.core.events import EventBus

        bus = EventBus()
        events = []
        bus.on("run_start", lambda **kw: events.append("start"))

        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 5),
                initial_cash=Decimal("1000000"),
            ),
            event_bus=bus,
        )
        env.run(DummyAgent())
        assert "start" in events
