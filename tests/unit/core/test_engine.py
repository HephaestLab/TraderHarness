"""Tests for BacktestEngine (TradingBus model)."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.engine import BacktestEngine, EngineConfig, DataProvider
from traderharness.core.events import EventBus
from traderharness.core.calendar import TradingCalendar
from traderharness.core.market_profile import AShareProfile


class FakeDataProvider:
    """Returns synthetic daily bars for testing."""

    def __init__(self):
        dates = [date(2024, 3, 4) + timedelta(days=i) for i in range(10)]
        self._df = pd.DataFrame({
            "date": dates,
            "open": [100.0 + i for i in range(10)],
            "high": [105.0 + i for i in range(10)],
            "low": [95.0 + i for i in range(10)],
            "close": [101.0 + i for i in range(10)],
            "volume": [10000] * 10,
        })

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        mask = (self._df["date"] >= start) & (self._df["date"] <= end)
        return self._df[mask].reset_index(drop=True)

    async def get_stock_list(self) -> list[dict]:
        return [{"code": "600519", "name": "600519"}]


class DummyAgent:
    def __init__(self, agent_id: str = "dummy"):
        self.agent_id = agent_id
        self.name = "DummyAgent"
        self.days_called: list[date] = []

    async def on_day(self, bus, current_date: date) -> None:
        self.days_called.append(current_date)


class BuyOnceAgent:
    def __init__(self):
        self.agent_id = "buyer"
        self.name = "BuyOnce"
        self._bought = False

    async def on_day(self, bus, current_date: date) -> None:
        if not self._bought:
            result = bus.place_order(
                agent_id=self.agent_id,
                stock_code="600519",
                side="buy",
                quantity=100,
            )
            if result.get("success"):
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
            start_date=date(2024, 3, 8),
            end_date=date(2024, 3, 11),
        )
        assert len(agent.days_called) == 2

    @pytest.mark.asyncio
    async def test_multiple_agents(self):
        engine = self._make_engine()
        a1 = DummyAgent("a1")
        a2 = DummyAgent("a2")
        await engine.run(agents=[a1, a2], start_date=date(2024, 3, 4), end_date=date(2024, 3, 5))
        assert len(a1.days_called) == 2
        assert len(a2.days_called) == 2

    @pytest.mark.asyncio
    async def test_emits_events(self):
        bus = EventBus()
        events_received = []
        bus.on("day_start", lambda **kw: events_received.append("day_start"))
        bus.on("day_end", lambda **kw: events_received.append("day_end"))
        bus.on("run_start", lambda **kw: events_received.append("run_start"))
        bus.on("run_end", lambda **kw: events_received.append("run_end"))

        engine = self._make_engine(event_bus=bus)
        await engine.run(agents=[DummyAgent()], start_date=date(2024, 3, 4), end_date=date(2024, 3, 5))
        assert "run_start" in events_received
        assert "run_end" in events_received
        assert "day_start" in events_received

    @pytest.mark.asyncio
    async def test_breakpoints(self):
        bus = EventBus()
        breakpoints_hit = []
        bus.on("breakpoint_hit", lambda **kw: breakpoints_hit.append(kw.get("date")))

        engine = self._make_engine(event_bus=bus)
        await engine.run(
            agents=[DummyAgent()],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
            breakpoints=[date(2024, 3, 6)],
        )
        assert date(2024, 3, 6) in breakpoints_hit

    @pytest.mark.asyncio
    async def test_agent_can_trade_via_bus(self):
        engine = self._make_engine()
        agent = BuyOnceAgent()
        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
        )
        equity = result.agent_data["buyer"]["equity_curve"]
        assert len(equity) == 5
        assert agent._bought is True

    @pytest.mark.asyncio
    async def test_result_contains_equity_curve(self):
        engine = self._make_engine()
        agent = DummyAgent()
        result = await engine.run(agents=[agent], start_date=date(2024, 3, 4), end_date=date(2024, 3, 5))
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
            data_provider=FakeDataProvider(),
            event_bus=event_bus or EventBus(),
        )
