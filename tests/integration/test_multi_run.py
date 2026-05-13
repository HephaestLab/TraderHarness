"""Integration test — multi-run statistical analysis."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from finharness.core.env import TradingEnv, EnvConfig
from finharness.metrics.performance import calculate_metrics


class FakeData:
    async def get_daily_bars(self, stock_code, start, end):
        dates = [date(2024, 3, 4) + timedelta(days=i) for i in range(10)]
        return pd.DataFrame({
            "date": dates, "open": [100.0]*10, "high": [105.0]*10,
            "low": [95.0]*10, "close": [101.0]*10, "volume": [10000]*10,
        })


class NoopAgent:
    def __init__(self, aid="noop"):
        self.agent_id = aid
        self.name = "Noop"

    async def on_day(self, bus, current_date):
        pass


class TestMultiRun:
    def test_multiple_runs_produce_results(self):
        results = []
        for i in range(3):
            env = TradingEnv(
                config=EnvConfig(
                    start_date=date(2024, 3, 4),
                    end_date=date(2024, 3, 8),
                    initial_cash=Decimal("1000000"),
                ),
                data_provider=FakeData(),
            )
            agent = NoopAgent(f"run_{i}")
            result = env.run(agent)
            equity = result.agent_data[agent.agent_id]["equity_curve"]
            metrics = calculate_metrics(equity, Decimal("1000000"), [])
            results.append(metrics)

        assert len(results) == 3
        for m in results:
            assert m.total_return_pct == 0.0

    def test_statistical_aggregation(self):
        returns = [5.0, 8.0, 3.0, 7.0, 6.0]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = variance ** 0.5
        assert 4.0 < mean < 7.0
        assert std > 0
