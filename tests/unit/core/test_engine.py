"""Tests for BacktestEngine (TradingBus model)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.calendar import TradingCalendar
from traderharness.core.engine import AgentExecutionError, BacktestEngine, EngineConfig
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile


class FakeDataProvider:
    """Returns synthetic daily bars + matching 5-minute bars for testing.

    Fair-matching invariant: TradingBus only fills orders against 5-minute
    sub-window bars (no daily open/close fallback), so fixtures that expect
    successful trades must also supply 5-minute bars for the open/close
    windows.
    """

    def __init__(self):
        dates = [date(2024, 3, 4) + timedelta(days=i) for i in range(10)]
        self._df = pd.DataFrame(
            {
                "date": dates,
                "open": [100.0 + i for i in range(10)],
                "high": [105.0 + i for i in range(10)],
                "low": [95.0 + i for i in range(10)],
                "close": [101.0 + i for i in range(10)],
                "volume": [10000] * 10,
            }
        )

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        mask = (self._df["date"] >= start) & (self._df["date"] <= end)
        return self._df[mask].reset_index(drop=True)

    async def get_stock_list(self) -> list[dict]:
        return [{"code": "600519", "name": "600519"}]

    async def get_5min_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        mask = (self._df["date"] >= start) & (self._df["date"] <= end)
        rows = []
        for _, row in self._df[mask].iterrows():
            d = row["date"]
            rows.append(
                {
                    "datetime": datetime.combine(d, datetime.min.time()).replace(hour=9, minute=40),
                    "date": d,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["open"],
                    "volume": 1000,
                }
            )
            rows.append(
                {
                    "datetime": datetime.combine(d, datetime.min.time()).replace(hour=14, minute=40),
                    "date": d,
                    "open": row["close"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": 1000,
                }
            )
        return pd.DataFrame(rows)


class DummyAgent:
    def __init__(self, agent_id: str = "dummy"):
        self.agent_id = agent_id
        self.name = "DummyAgent"
        self.days_called: list[date] = []

    async def on_day(self, bus, current_date: date) -> None:
        self.days_called.append(current_date)


class MaskCaptureAgent(DummyAgent):
    def __init__(self, agent_id: str):
        super().__init__(agent_id)
        self.entity_maskers = []

    async def on_day(self, bus, current_date: date) -> None:
        await super().on_day(bus, current_date)
        self.entity_maskers.append(getattr(bus, "_entity_masker", None))


class OrderProbeAgent(DummyAgent):
    """Records the order in which agents enter on_day within a trading day."""

    def __init__(self, agent_id: str, order: list[str]):
        super().__init__(agent_id)
        self.order = order

    async def on_day(self, bus, current_date: date) -> None:
        self.order.append(self.agent_id)
        await super().on_day(bus, current_date)


class CancellingAgent(DummyAgent):
    def __init__(self, state):
        super().__init__("cancelling")
        self.state = state

    async def on_day(self, bus, current_date: date) -> None:
        await super().on_day(bus, current_date)
        self.state["cancelled"] = True


class FailingAgent(DummyAgent):
    """Raises once on a specific day index; records every day it was called."""

    def __init__(self, agent_id: str, fail_on_day_index: int = 0):
        super().__init__(agent_id)
        self._fail_on_day_index = fail_on_day_index
        self._calls = 0

    async def on_day(self, bus, current_date: date) -> None:
        await super().on_day(bus, current_date)
        day_index = self._calls
        self._calls += 1
        if day_index == self._fail_on_day_index:
            raise ValueError(f"boom on {current_date}")


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
    async def test_multiple_agents_are_scheduled_sequentially_each_day(self):
        order: list[str] = []
        agents = [
            OrderProbeAgent("a1", order),
            OrderProbeAgent("a2", order),
        ]

        await self._make_engine().run(
            agents=agents,
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
        )

        assert order == ["a1", "a2"]
        assert all(agent.days_called == [date(2024, 3, 4)] for agent in agents)

    @pytest.mark.asyncio
    async def test_cooperative_cancellation_stops_before_next_trading_day(self):
        state = {"cancelled": False}
        config = EngineConfig(
            initial_cash=Decimal("1000000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            cancel_check=lambda: state["cancelled"],
        )
        engine = BacktestEngine(config=config, data_provider=FakeDataProvider())
        agent = CancellingAgent(state)
        events = []
        engine._event_bus.on("run_end", lambda **data: events.append(data))

        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
        )

        assert agent.days_called == [date(2024, 3, 4)]
        assert result.trading_days == 1
        assert events == [{"trading_days": 1, "cancelled": True}]

    @pytest.mark.asyncio
    async def test_entity_masker_is_run_scoped_and_shared_by_all_agents(self):
        config = EngineConfig(
            initial_cash=Decimal("1000000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            mask_entities=True,
            entity_mask_seed=123,
        )
        engine = BacktestEngine(config=config, data_provider=FakeDataProvider())
        a1 = MaskCaptureAgent("a1")
        a2 = MaskCaptureAgent("a2")

        await engine.run([a1, a2], date(2024, 3, 4), date(2024, 3, 4))

        assert a1.entity_maskers[0] is a2.entity_maskers[0]
        assert engine._entity_masker is a1.entity_maskers[0]
        assert a1.entity_maskers[0].enabled is True

    @pytest.mark.asyncio
    async def test_entity_masker_is_absent_by_default(self):
        agent = MaskCaptureAgent("plain")

        engine = self._make_engine()
        await engine.run([agent], date(2024, 3, 4), date(2024, 3, 4))

        assert agent.entity_maskers == [None]
        assert engine._entity_masker is None

    @pytest.mark.asyncio
    async def test_emits_events(self):
        bus = EventBus()
        events_received = []
        bus.on("day_start", lambda **kw: events_received.append("day_start"))
        bus.on("day_end", lambda **kw: events_received.append("day_end"))
        bus.on("run_start", lambda **kw: events_received.append("run_start"))
        bus.on("run_end", lambda **kw: events_received.append("run_end"))

        engine = self._make_engine(event_bus=bus)
        await engine.run(
            agents=[DummyAgent()], start_date=date(2024, 3, 4), end_date=date(2024, 3, 5)
        )
        assert "run_start" in events_received
        assert "run_end" in events_received
        assert "day_start" in events_received

    @pytest.mark.asyncio
    async def test_day_end_reports_progress_and_per_agent_equity(self):
        """day_end must carry enough state for a live UI: which day out of
        how many, plus each agent's end-of-day equity and return."""
        bus = EventBus()
        run_starts = []
        day_ends = []
        bus.on("run_start", lambda **kw: run_starts.append(kw))
        bus.on("day_end", lambda **kw: day_ends.append(kw))

        engine = self._make_engine(event_bus=bus)
        await engine.run(
            agents=[DummyAgent("a1"), DummyAgent("a2")],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
        )

        assert run_starts[0]["total_days"] == 2
        assert len(day_ends) == 2
        first = day_ends[0]
        assert first["date"] == date(2024, 3, 4)
        assert first["day_index"] == 0
        assert first["total_days"] == 2
        assert set(first["equity"]) == {"a1", "a2"}
        snapshot = first["equity"]["a1"]
        assert snapshot["equity"] == pytest.approx(1_000_000.0)
        assert snapshot["return_pct"] == pytest.approx(0.0)

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
    async def test_agent_exception_fails_closed_instead_of_silently_continuing(self):
        engine = self._make_engine()
        healthy = DummyAgent("healthy")
        failing = FailingAgent("failing", fail_on_day_index=1)

        with pytest.raises(AgentExecutionError) as exc_info:
            await engine.run(
                agents=[healthy, failing],
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 8),
            )

        result = exc_info.value.result
        assert "failing" in result.failed_agents
        assert "ValueError" in result.failed_agents["failing"]
        assert "error" in result.agent_data["failing"]
        # The engine should not silently swallow the exception mid-run — other
        # agents keep running to completion (independent portfolios), and the
        # failure is surfaced rather than hidden behind an apparently-successful run.
        assert len(healthy.days_called) == 5
        assert len(failing.days_called) == 5

    @pytest.mark.asyncio
    async def test_result_contains_equity_curve(self):
        engine = self._make_engine()
        agent = DummyAgent()
        result = await engine.run(
            agents=[agent], start_date=date(2024, 3, 4), end_date=date(2024, 3, 5)
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
            data_provider=FakeDataProvider(),
            event_bus=event_bus or EventBus(),
        )
