"""Integration test — full backtest end-to-end with real data flow."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from finharness.core.env import TradingEnv, EnvConfig
from finharness.metrics.performance import calculate_metrics


class RealisticDataProvider:
    """Provides multi-stock daily bars for realistic E2E testing."""

    def __init__(self):
        dates = [date(2024, 3, 4) + timedelta(days=i) for i in range(14)]
        trading_dates = [d for d in dates if d.weekday() < 5]

        self._data = {}
        self._data["600519"] = pd.DataFrame({
            "date": trading_dates,
            "open": [1800 + i*5 for i in range(len(trading_dates))],
            "high": [1820 + i*5 for i in range(len(trading_dates))],
            "low": [1780 + i*5 for i in range(len(trading_dates))],
            "close": [1810 + i*5 for i in range(len(trading_dates))],
            "volume": [50000] * len(trading_dates),
        })
        self._data["000001"] = pd.DataFrame({
            "date": trading_dates,
            "open": [10.0 + i*0.1 for i in range(len(trading_dates))],
            "high": [10.5 + i*0.1 for i in range(len(trading_dates))],
            "low": [9.8 + i*0.1 for i in range(len(trading_dates))],
            "close": [10.2 + i*0.1 for i in range(len(trading_dates))],
            "volume": [100000] * len(trading_dates),
        })

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame:
        df = self._data.get(stock_code)
        if df is None:
            return pd.DataFrame()
        mask = (df["date"] >= start) & (df["date"] <= end)
        return df[mask].reset_index(drop=True)


class BuyAndHoldAgent:
    def __init__(self):
        self.agent_id = "bh_test"
        self.name = "BuyAndHoldTest"
        self._bought = False

    async def on_day(self, bus, current_date: date) -> None:
        if not self._bought:
            result = await bus.place_order(
                agent_id=self.agent_id, stock_code="600519",
                side="buy", quantity=100,
            )
            if result.get("success"):
                self._bought = True


class DataQueryAgent:
    """Agent that queries market data through the bus."""

    def __init__(self):
        self.agent_id = "data_query"
        self.name = "DataQueryAgent"
        self.prices_seen = []
        self.klines_received = 0

    async def on_day(self, bus, current_date: date) -> None:
        bars = await bus.get_daily_bars("600519", days=5)
        if not bars.empty:
            self.klines_received += len(bars)
        price_info = await bus.get_stock_price("600519")
        if price_info:
            self.prices_seen.append(price_info["close"])


class TestFullBacktest:
    def test_end_to_end_buy_and_hold(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 15)),
            data_provider=RealisticDataProvider(),
        )
        agent = BuyAndHoldAgent()
        result = env.run(agent)
        assert result.trading_days == 10
        equity = result.agent_data["bh_test"]["equity_curve"]
        assert len(equity) == 10
        assert agent._bought is True

    def test_metrics_from_result(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 15)),
            data_provider=RealisticDataProvider(),
        )
        agent = BuyAndHoldAgent()
        result = env.run(agent)
        equity = result.agent_data["bh_test"]["equity_curve"]
        metrics = calculate_metrics(equity, Decimal("1000000"), [])
        assert metrics.trading_days == 10
        assert metrics.final_value > 0

    def test_agent_receives_market_data(self):
        """Agent can query K-lines and prices through the bus."""
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 8)),
            data_provider=RealisticDataProvider(),
        )
        agent = DataQueryAgent()
        env.run(agent)
        assert agent.klines_received > 0
        assert len(agent.prices_seen) >= 4

    def test_multi_agent_isolation(self):
        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 8)),
            data_provider=RealisticDataProvider(),
        )
        a1 = BuyAndHoldAgent()
        a1.agent_id = "agent_1"

        class PassiveAgent:
            agent_id = "passive"
            name = "Passive"
            async def on_day(self, bus, current_date): pass

        result = env.run([a1, PassiveAgent()])
        assert "agent_1" in result.agent_data
        assert "passive" in result.agent_data
