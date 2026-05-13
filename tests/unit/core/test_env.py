"""Tests for TradingEnv — main entry point."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from finharness.core.env import TradingEnv, EnvConfig


class FakeData:
    async def get_daily_bars(self, stock_code, start, end):
        dates = [date(2024, 3, 4) + timedelta(days=i) for i in range(10)]
        return pd.DataFrame({
            "date": dates, "open": [100.0]*10, "high": [105.0]*10,
            "low": [95.0]*10, "close": [101.0]*10, "volume": [10000]*10,
        })

    async def get_stock_list(self):
        return [{"code": "test", "name": "test"}]


class DummyAgent:
    def __init__(self, agent_id="test"):
        self.agent_id = agent_id
        self.name = "TestAgent"
        self.days_called = []

    async def on_day(self, bus, current_date):
        self.days_called.append(current_date)


class TestTradingEnv:
    def test_sync_run(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 8)),
            data_provider=FakeData(),
        )
        agent = DummyAgent()
        result = env.run(agent)
        assert result.trading_days == 5
        assert len(agent.days_called) == 5

    def test_multiple_agents(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 5)),
            data_provider=FakeData(),
        )
        a1 = DummyAgent("a1")
        a2 = DummyAgent("a2")
        result = env.run([a1, a2])
        assert len(a1.days_called) == 2
        assert len(a2.days_called) == 2

    @pytest.mark.asyncio
    async def test_async_run(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 6)),
            data_provider=FakeData(),
        )
        agent = DummyAgent()
        result = await env.run_async(agent)
        assert result.trading_days == 3

    def test_custom_event_bus(self):
        from finharness.core.events import EventBus
        bus = EventBus()
        events = []
        bus.on("run_start", lambda **kw: events.append("start"))
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 5)),
            data_provider=FakeData(),
            event_bus=bus,
        )
        env.run(DummyAgent())
        assert "start" in events
