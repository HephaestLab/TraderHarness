"""Tests for comparison metrics."""

from datetime import date, timedelta
from decimal import Decimal

from traderharness.metrics.comparison import MultiAgentComparison, compare_vs_benchmark
from traderharness.metrics.performance import PerformanceMetrics


def _curve(start: date, days: int, start_val: float, end_val: float):
    step = (end_val - start_val) / max(days - 1, 1)
    return [
        (start + timedelta(days=i), Decimal(str(round(start_val + step * i, 2))))
        for i in range(days)
    ]


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

    def test_information_ratio_aligns_returns_by_date(self):
        agent = [
            (date(2024, 3, 2), Decimal("100")),
            (date(2024, 3, 3), Decimal("110")),
            (date(2024, 3, 4), Decimal("121")),
        ]
        benchmark = [
            (date(2024, 3, 1), Decimal("100")),
            (date(2024, 3, 2), Decimal("100")),
            (date(2024, 3, 3), Decimal("101")),
            (date(2024, 3, 4), Decimal("102.01")),
        ]

        result = compare_vs_benchmark(agent, benchmark, Decimal("100"))

        assert result.information_ratio == 0.0


def test_sharpe_ranking_breaks_ties_by_total_return():
    def metrics(total_return):
        return PerformanceMetrics(
            total_return_pct=total_return,
            annual_return_pct=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            calmar_ratio=0,
            max_drawdown_pct=0,
            max_consecutive_loss_days=0,
            win_rate=0,
            profit_loss_ratio=0,
            turnover_rate=0,
            total_trades=0,
            trading_days=1,
            final_value=100,
        )

    comparison = MultiAgentComparison(
        agents=["lower", "higher"],
        metrics={"lower": metrics(0.2), "higher": metrics(0.3)},
    )

    assert comparison.rank_by() == [("higher", 0), ("lower", 0)]
