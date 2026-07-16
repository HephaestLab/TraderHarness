"""TDD tests for behavior metrics."""

from datetime import date
from decimal import Decimal

import pytest

from traderharness.metrics.behavior import calculate_behavior, BehaviorMetrics


@pytest.fixture
def sample_trades():
    return [
        {"action": "buy", "stock_code": "600519", "date": "2024-01-05", "amount": 180000, "quantity": 100, "price": 1800},
        {"action": "buy", "stock_code": "000001", "date": "2024-01-08", "amount": 15000, "quantity": 1000, "price": 15},
        {"action": "sell", "stock_code": "600519", "date": "2024-01-15", "amount": 185000, "quantity": 100, "price": 1850, "pnl": 5000},
        {"action": "sell", "stock_code": "000001", "date": "2024-01-20", "amount": 14000, "quantity": 1000, "price": 14, "pnl": -1000},
        {"action": "buy", "stock_code": "300750", "date": "2024-01-22", "amount": 100000, "quantity": 500, "price": 200},
    ]


@pytest.fixture
def sample_curve():
    return [(date(2024, 1, d), Decimal(str(1000000 + (d - 2) * 500))) for d in range(2, 32)]


class TestBehaviorMetrics:
    def test_basic_calculation(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        assert isinstance(result, BehaviorMetrics)

    def test_trade_counts(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        assert result.total_buy_count == 3
        assert result.total_sell_count == 2

    def test_holding_days(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        # 600519: buy 01-05, sell 01-15 = 10 days
        # 000001: buy 01-08, sell 01-20 = 12 days
        # avg = (10 + 12) / 2 = 11
        assert result.avg_holding_days == 11.0

    def test_most_traded_stocks(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        stock_codes = [code for code, _ in result.most_traded_stocks]
        assert "600519" in stock_codes
        assert "000001" in stock_codes

    def test_avg_trade_size(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        # Average amount of trades with amount field: (180000+15000+185000+14000+100000)/5 = 98800
        # As % of 1M initial: 9.88%
        assert result.avg_trade_size_pct > 0

    def test_empty_trades(self, sample_curve):
        result = calculate_behavior([], sample_curve, Decimal("1000000"))
        assert result.total_buy_count == 0
        assert result.total_sell_count == 0
        assert result.avg_holding_days == 0.0
        assert result.most_traded_stocks == []

    def test_empty_curve(self, sample_trades):
        result = calculate_behavior(sample_trades, [], Decimal("1000000"))
        assert result.total_buy_count == 3


class TestBehaviorMetricsBenchmark:
    def test_max_position_pct(self, sample_trades, sample_curve):
        result = calculate_behavior(sample_trades, sample_curve, Decimal("1000000"))
        # 600519 buy: 180000 / 1000000 = 18%
        assert result.max_single_position_pct >= 18.0
