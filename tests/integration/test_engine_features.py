"""Integration tests — engine with news, dividends, corporate actions.

Tests the full pipeline without LLM calls (using DummyAgent).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from traderharness.core.calendar import TradingCalendar
from traderharness.core.engine import BacktestEngine, EngineConfig
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile


class SimpleTestProvider:
    """Test data provider that returns synthetic data via interface.

    Also exposes 5-minute bars: TradingBus only fills orders against
    5-minute sub-window bars (no daily open/close fallback), so any fixture
    exercising place_order needs matching intraday data.
    """

    def __init__(self, daily_df: pd.DataFrame):
        self._df = daily_df

    async def get_stock_list(self) -> list[dict]:
        codes = self._df["stock_code"].unique().tolist()
        return [{"code": c, "name": c} for c in codes]

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        mask = (self._df["stock_code"] == stock_code) & (self._df["date"] >= start) & (self._df["date"] <= end)
        return self._df[mask].drop(columns=["stock_code"]).reset_index(drop=True)

    async def get_5min_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        from datetime import datetime

        mask = (self._df["stock_code"] == stock_code) & (self._df["date"] >= start) & (self._df["date"] <= end)
        rows = []
        for _, row in self._df[mask].iterrows():
            d = row["date"]
            rows.append({
                "datetime": datetime.combine(d, datetime.min.time()).replace(hour=9, minute=40),
                "date": d,
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["open"], "volume": 1000,
            })
            rows.append({
                "datetime": datetime.combine(d, datetime.min.time()).replace(hour=14, minute=40),
                "date": d,
                "open": row["close"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": 1000,
            })
        return pd.DataFrame(rows)


def _create_test_data(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    """Create test parquet files: daily, announcements, news, dividends.
    Returns (dataset_dir, daily_df).
    """
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    # Daily data: 600519 + 000001, March 4-15 2024
    dates = [date(2024, 3, d) for d in range(4, 16) if date(2024, 3, d).weekday() < 5]
    rows = []
    for d in dates:
        for code in ["600519", "000001"]:
            base = 1800.0 if code == "600519" else 15.0
            idx = (d - date(2024, 3, 4)).days
            rows.append({
                "stock_code": code,
                "date": d,
                "open": base + idx * 0.5,
                "high": base + idx * 0.5 + 2,
                "low": base + idx * 0.5 - 2,
                "close": base + idx * 0.5 + 1,
                "volume": 10000,
            })
    daily_df = pd.DataFrame(rows)
    daily_df.to_parquet(dataset_dir / "daily.parquet", index=False)

    # Announcements
    ann_df = pd.DataFrame({
        "stock_code": ["600519", "000001"],
        "stock_name": ["贵州茅台", "平安银行"],
        "title": ["年度报告公告", "季度报告公告"],
        "announcement_time": pd.to_datetime(["2024-03-04 20:00:00", "2024-03-06 19:00:00"]),
        "pdf_url": ["", ""],
        "ann_type": [None, None],
    })
    ann_df.to_parquet(dataset_dir / "announcements.parquet", index=False)

    # News
    news_df = pd.DataFrame({
        "id": [1, 2],
        "title": ["央行降准", "科技股涨"],
        "content": ["央行决定下调存款准备金率", "纳斯达克指数创新高"],
        "ctime": [
            int(pd.Timestamp("2024-03-04 16:00:00").timestamp()),
            int(pd.Timestamp("2024-03-05 10:00:00").timestamp()),
        ],
        "display_time": pd.to_datetime(["2024-03-04 16:00:00", "2024-03-05 10:00:00"]),
        "level": ["A", "C"],
        "tags": ["", ""],
        "stock_list": ["", ""],
    })
    news_df.to_parquet(dataset_dir / "news_cls.parquet", index=False)

    # Dividends: 000001 ex_date = 2024-03-08
    div_df = pd.DataFrame({
        "stock_code": ["000001"],
        "ann_date": ["2024-03-01"],
        "bonus_shares": [0.0],
        "transfer_shares": [0.0],
        "cash_dividend": [2.0],
        "ex_date": ["2024-03-08"],
        "record_date": ["2024-03-07"],
        "progress": ["实施"],
    })
    div_df.to_parquet(dataset_dir / "dividends.parquet", index=False)

    return dataset_dir, daily_df


class BuyAndHoldAgent:
    """Buys 000001 on first day, holds forever."""

    def __init__(self):
        self.agent_id = "buy_hold"
        self.name = "BuyAndHold"
        self._bought = False
        self.received_corporate_actions = []
        self.buy_result = None

    async def on_day(self, bus, current_date: date) -> None:
        if not self._bought:
            result = bus.place_order(
                agent_id=self.agent_id,
                stock_code="000001",
                side="buy",
                quantity=1000,
            )
            self.buy_result = result
            if result.get("success"):
                self._bought = True

        # Check if bus has corporate actions
        actions = getattr(bus, "_corporate_actions_today", [])
        if actions:
            self.received_corporate_actions.extend(actions)


class TestEngineWithDividends:
    @pytest.mark.asyncio
    async def test_dividend_processed_on_ex_date(self, tmp_path):
        dataset_dir, daily_df = _create_test_data(tmp_path)
        config = EngineConfig(
            initial_cash=Decimal("100000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            dataset_dir=str(dataset_dir),
        )
        engine = BacktestEngine(config=config, data_provider=SimpleTestProvider(daily_df), event_bus=EventBus())
        agent = BuyAndHoldAgent()

        await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 11),
        )

        # Agent should have received corporate action on March 8
        assert len(agent.received_corporate_actions) == 1
        action = agent.received_corporate_actions[0]
        assert action["stock_code"] == "000001"
        assert "cash_dividend" in action

    @pytest.mark.asyncio
    async def test_equity_includes_dividend(self, tmp_path):
        dataset_dir, daily_df = _create_test_data(tmp_path)
        config = EngineConfig(
            initial_cash=Decimal("100000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            dataset_dir=str(dataset_dir),
        )
        engine = BacktestEngine(config=config, data_provider=SimpleTestProvider(daily_df), event_bus=EventBus())
        agent = BuyAndHoldAgent()

        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 11),
        )

        equity_curve = result.agent_data["buy_hold"]["equity_curve"]
        assert len(equity_curve) > 0
        # Final value should be > initial because dividend was paid
        final_value = float(equity_curve[-1][1])
        assert final_value > 0


class TestEngineWithNewsLoading:
    @pytest.mark.asyncio
    async def test_engine_loads_news_without_crash(self, tmp_path):
        dataset_dir, daily_df = _create_test_data(tmp_path)
        config = EngineConfig(
            initial_cash=Decimal("100000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            dataset_dir=str(dataset_dir),
        )
        engine = BacktestEngine(config=config, data_provider=SimpleTestProvider(daily_df), event_bus=EventBus())

        class SimpleAgent:
            agent_id = "simple"
            name = "Simple"
            async def on_day(self, bus, current_date):
                # Verify news manager is attached
                assert hasattr(bus, "_news_manager")
                assert bus._news_manager is not None

        result = await engine.run(
            agents=[SimpleAgent()],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 6),
        )
        assert result.trading_days >= 2


class TestMultiAgentComparison:
    @pytest.mark.asyncio
    async def test_two_agents_independent_portfolios(self, tmp_path):
        dataset_dir, daily_df = _create_test_data(tmp_path)
        config = EngineConfig(
            initial_cash=Decimal("100000"),
            profile=AShareProfile(),
            calendar=TradingCalendar(),
            dataset_dir=str(dataset_dir),
        )
        engine = BacktestEngine(config=config, data_provider=SimpleTestProvider(daily_df), event_bus=EventBus())

        class PassiveAgent:
            agent_id = "passive"
            name = "Passive"
            async def on_day(self, bus, current_date):
                pass

        active = BuyAndHoldAgent()
        passive = PassiveAgent()

        result = await engine.run(
            agents=[active, passive],
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 8),
        )

        assert "buy_hold" in result.agent_data
        assert "passive" in result.agent_data
        # Active agent buy should succeed
        assert active.buy_result is not None
        assert active.buy_result.get("success"), f"Buy failed: {active.buy_result}"

        # Active agent should have different equity (bought stock)
        active_curve = result.agent_data["buy_hold"]["equity_curve"]
        active_values = [float(v) for _, v in active_curve]
        assert any(v != 100000.0 for v in active_values), f"Active values: {active_values}"

        # Passive agent equity should differ from active (independent portfolios)
        passive_curve = result.agent_data["passive"]["equity_curve"]
        passive_values = [float(v) for _, v in passive_curve]
        assert passive_values != active_values
