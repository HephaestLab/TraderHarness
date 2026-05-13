"""Integration test — full backtest end-to-end."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.core.env import TradingEnv, EnvConfig
from finharness.core.engine import MarketDataProvider
from finharness.metrics.performance import calculate_metrics


class FakeMarketData:
    """Simulates price data for integration testing."""

    _PRICES = {
        "600519": {date(2024, 3, 4): Decimal("1800"), date(2024, 3, 5): Decimal("1820"),
                   date(2024, 3, 6): Decimal("1790"), date(2024, 3, 7): Decimal("1850"),
                   date(2024, 3, 8): Decimal("1860")},
        "000001": {date(2024, 3, 4): Decimal("10.00"), date(2024, 3, 5): Decimal("10.20"),
                   date(2024, 3, 6): Decimal("10.10"), date(2024, 3, 7): Decimal("10.50"),
                   date(2024, 3, 8): Decimal("10.30")},
    }

    def get_price(self, stock_code: str, trade_date: date) -> Decimal | None:
        return self._PRICES.get(stock_code, {}).get(trade_date)

    def get_prev_close(self, stock_code: str, trade_date: date) -> Decimal | None:
        prices = self._PRICES.get(stock_code, {})
        sorted_dates = sorted(d for d in prices if d < trade_date)
        return prices[sorted_dates[-1]] if sorted_dates else None


class BuyAndHoldAgent:
    def __init__(self):
        self.agent_id = "bh_test"
        self.name = "BuyAndHoldTest"
        self._bought = False

    async def on_day(self, env, current_date: date) -> None:
        if not self._bought:
            await env.place_order(
                agent_id=self.agent_id, stock_code="600519",
                side="buy", quantity=100,
            )
            self._bought = True


class TestFullBacktest:
    def test_end_to_end_run(self):
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 8),
                initial_cash=Decimal("1000000"),
            ),
            market_data=FakeMarketData(),
        )
        agent = BuyAndHoldAgent()
        result = env.run(agent)
        assert result.trading_days == 5
        assert "bh_test" in result.agent_data
        equity = result.agent_data["bh_test"]["equity_curve"]
        assert len(equity) == 5

    def test_metrics_from_result(self):
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 8),
                initial_cash=Decimal("1000000"),
            ),
            market_data=FakeMarketData(),
        )
        agent = BuyAndHoldAgent()
        result = env.run(agent)
        equity = result.agent_data["bh_test"]["equity_curve"]
        trades = result.agent_data["bh_test"]["trades"]
        metrics = calculate_metrics(equity, Decimal("1000000"), trades)
        assert metrics.trading_days == 5
        assert metrics.final_value > 0

    def test_multi_agent_run(self):
        env = TradingEnv(
            config=EnvConfig(
                start_date=date(2024, 3, 4),
                end_date=date(2024, 3, 6),
                initial_cash=Decimal("1000000"),
            ),
            market_data=FakeMarketData(),
        )

        class PassiveAgent:
            def __init__(self, aid):
                self.agent_id = aid
                self.name = aid

            async def on_day(self, env, current_date):
                pass

        a1 = BuyAndHoldAgent()
        a2 = PassiveAgent("passive")
        result = env.run([a1, a2])
        assert "bh_test" in result.agent_data
        assert "passive" in result.agent_data
