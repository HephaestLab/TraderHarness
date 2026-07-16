"""Comparison metrics — agent vs benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class ComparisonResult:
    alpha: float
    information_ratio: float
    agent_return_pct: float
    benchmark_return_pct: float


def compare_vs_benchmark(
    agent_curve: list[tuple[date, Decimal]],
    benchmark_curve: list[tuple[date, Decimal]],
    initial_cash: Decimal,
) -> ComparisonResult:
    """Compare agent performance against benchmark."""
    if not agent_curve or not benchmark_curve:
        return ComparisonResult(alpha=0.0, information_ratio=0.0,
                                agent_return_pct=0.0, benchmark_return_pct=0.0)

    initial = float(initial_cash)
    agent_final = float(agent_curve[-1][1])
    bench_final = float(benchmark_curve[-1][1])

    agent_return = (agent_final - initial) / initial
    bench_return = (bench_final - initial) / initial

    alpha = (agent_return - bench_return) * 100

    agent_daily = _daily_returns(agent_curve)
    bench_daily = _daily_returns(benchmark_curve)

    min_len = min(len(agent_daily), len(bench_daily))
    if min_len < 2:
        return ComparisonResult(
            alpha=round(alpha, 2),
            information_ratio=0.0,
            agent_return_pct=round(agent_return * 100, 2),
            benchmark_return_pct=round(bench_return * 100, 2),
        )

    excess = [agent_daily[i] - bench_daily[i] for i in range(min_len)]
    mean_excess = sum(excess) / len(excess)
    var_excess = sum((e - mean_excess) ** 2 for e in excess) / (len(excess) - 1)
    tracking_error = var_excess ** 0.5 * (252 ** 0.5)
    ir = (mean_excess * 252) / tracking_error if tracking_error > 0 else 0.0

    return ComparisonResult(
        alpha=round(alpha, 2),
        information_ratio=round(ir, 2),
        agent_return_pct=round(agent_return * 100, 2),
        benchmark_return_pct=round(bench_return * 100, 2),
    )


def _daily_returns(curve: list[tuple[date, Decimal]]) -> list[float]:
    values = [float(v) for _, v in curve]
    returns = []
    for i in range(1, len(values)):
        if values[i - 1] != 0:
            returns.append((values[i] - values[i - 1]) / values[i - 1])
    return returns
