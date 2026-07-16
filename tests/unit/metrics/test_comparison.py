"""Tests for comparison metrics."""

from datetime import date, timedelta
from decimal import Decimal

from traderharness.metrics.comparison import compare_vs_benchmark


def _curve(start: date, days: int, start_val: float, end_val: float):
    step = (end_val - start_val) / max(days - 1, 1)
    return [(start + timedelta(days=i), Decimal(str(round(start_val + step * i, 2)))) for i in range(days)]


class TestCompareVsBenchmark:
    def test_outperformance(self):
        agent = _curve(date(2024, 1, 2), 100, 1000000, 1200000)
        bench = _curve(date(2024, 1, 2), 100, 1000000, 1100000)
        result = compare_vs_benchmark(agent, bench, Decimal("1000000"))
        assert result.alpha > 0
        assert result.agent_return_pct > result.benchmark_return_pct

    def test_underperformance(self):
        agent = _curve(date(2024, 1, 2), 100, 1000000, 900000)
        bench = _curve(date(2024, 1, 2), 100, 1000000, 1050000)
        result = compare_vs_benchmark(agent, bench, Decimal("1000000"))
        assert result.alpha < 0

    def test_empty_curves(self):
        result = compare_vs_benchmark([], [], Decimal("1000000"))
        assert result.alpha == 0.0
