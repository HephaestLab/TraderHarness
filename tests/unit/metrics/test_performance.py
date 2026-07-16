"""Tests for performance metrics."""

from datetime import date, timedelta
from decimal import Decimal

from traderharness.metrics.performance import calculate_metrics, PerformanceMetrics


def _make_curve(start: date, days: int, start_val: float, end_val: float):
    """Generate a linear equity curve."""
    curve = []
    step = (end_val - start_val) / max(days - 1, 1)
    for i in range(days):
        d = start + timedelta(days=i)
        val = start_val + step * i
        curve.append((d, Decimal(str(round(val, 2)))))
    return curve


class TestCalculateMetrics:
    def test_positive_return(self):
        curve = _make_curve(date(2024, 1, 2), 100, 1000000, 1100000)
        m = calculate_metrics(curve, Decimal("1000000"), [])
        assert m.total_return_pct == 10.0
        assert m.final_value == 1100000.0

    def test_negative_return(self):
        curve = _make_curve(date(2024, 1, 2), 100, 1000000, 900000)
        m = calculate_metrics(curve, Decimal("1000000"), [])
        assert m.total_return_pct == -10.0

    def test_max_drawdown(self):
        curve = [
            (date(2024, 1, 2), Decimal("1000000")),
            (date(2024, 1, 3), Decimal("1100000")),
            (date(2024, 1, 4), Decimal("900000")),  # -18.18% from peak
            (date(2024, 1, 5), Decimal("950000")),
        ]
        m = calculate_metrics(curve, Decimal("1000000"), [])
        assert m.max_drawdown_pct > 18.0

    def test_max_consecutive_loss_days(self):
        curve = [
            (date(2024, 1, i), Decimal(str(1000000 - i * 1000)))
            for i in range(1, 8)
        ]
        m = calculate_metrics(curve, Decimal("1000000"), [])
        assert m.max_consecutive_loss_days == 6

    def test_win_rate(self):
        trades = [
            {"action": "sell", "pnl": 100},
            {"action": "sell", "pnl": -50},
            {"action": "sell", "pnl": 200},
        ]
        curve = _make_curve(date(2024, 1, 2), 10, 1000000, 1050000)
        m = calculate_metrics(curve, Decimal("1000000"), trades)
        assert m.win_rate == pytest.approx(66.7, abs=0.1)
        assert m.total_trades == 3

    def test_empty_curve(self):
        m = calculate_metrics([], Decimal("1000000"), [])
        assert m.total_return_pct == 0.0
        assert m.trading_days == 0

    def test_sharpe_positive(self):
        curve = _make_curve(date(2024, 1, 2), 252, 1000000, 1200000)
        m = calculate_metrics(curve, Decimal("1000000"), [])
        assert m.sharpe_ratio > 0


import pytest
