"""Comparison metrics — agent vs benchmark, multi-agent ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pandas as pd

from traderharness.metrics.performance import PerformanceMetrics, calculate_metrics


@dataclass
class ComparisonResult:
    alpha: float
    information_ratio: float
    agent_return_pct: float
    benchmark_return_pct: float


@dataclass
class MultiAgentComparison:
    """Multi-agent comparison table."""

    agents: list[str] = field(default_factory=list)
    metrics: dict[str, PerformanceMetrics] = field(default_factory=dict)
    vs_benchmark: dict[str, ComparisonResult] = field(default_factory=dict)
    ranking: list[tuple[str, float]] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Generate comparison table as DataFrame."""
        rows = []
        for agent_id in self.agents:
            m = self.metrics.get(agent_id)
            vs = self.vs_benchmark.get(agent_id)
            if m is None:
                continue
            row = {
                "Agent": agent_id,
                "Total Return%": m.total_return_pct,
                "Annual Return%": m.annual_return_pct,
                "Sharpe": m.sharpe_ratio,
                "Sortino": m.sortino_ratio,
                "Max DD%": m.max_drawdown_pct,
                "Win Rate%": m.win_rate,
                "P/L Ratio": m.profit_loss_ratio,
                "Trades": m.total_trades,
                "Final Value": m.final_value,
            }
            if vs:
                row["Alpha%"] = vs.alpha
                row["IR"] = vs.information_ratio
                row["Bench Return%"] = vs.benchmark_return_pct
            rows.append(row)
        return pd.DataFrame(rows)

    def rank_by(self, metric: str = "sharpe_ratio") -> list[tuple[str, float]]:
        """Rank agents by a metric."""
        scores = []
        for agent_id, m in self.metrics.items():
            val = getattr(m, metric, 0.0)
            scores.append((agent_id, val))
        scores.sort(
            key=lambda item: (
                item[1],
                self.metrics[item[0]].total_return_pct,
            ),
            reverse=True,
        )
        self.ranking = scores
        return scores


def compare_vs_benchmark(
    agent_curve: list[tuple[date, Decimal]],
    benchmark_curve: list[tuple[date, Decimal]],
    initial_cash: Decimal,
) -> ComparisonResult:
    """Compare agent performance against benchmark."""
    if not agent_curve or not benchmark_curve:
        return ComparisonResult(
            alpha=0.0, information_ratio=0.0, agent_return_pct=0.0, benchmark_return_pct=0.0
        )

    initial = float(initial_cash)
    agent_final = float(agent_curve[-1][1])
    bench_final = float(benchmark_curve[-1][1])

    agent_return = (agent_final - initial) / initial
    bench_return = (bench_final - initial) / initial

    alpha = (agent_return - bench_return) * 100

    agent_daily = _daily_returns(agent_curve)
    bench_daily = _daily_returns(benchmark_curve)

    common_dates = sorted(set(agent_daily) & set(bench_daily))
    if len(common_dates) < 2:
        return ComparisonResult(
            alpha=round(alpha, 2),
            information_ratio=0.0,
            agent_return_pct=round(agent_return * 100, 2),
            benchmark_return_pct=round(bench_return * 100, 2),
        )

    excess = [agent_daily[day] - bench_daily[day] for day in common_dates]
    mean_excess = sum(excess) / len(excess)
    var_excess = sum((e - mean_excess) ** 2 for e in excess) / (len(excess) - 1)
    tracking_error = var_excess**0.5 * (252**0.5)
    ir = (mean_excess * 252) / tracking_error if tracking_error > 1e-12 else 0.0

    return ComparisonResult(
        alpha=round(alpha, 2),
        information_ratio=round(ir, 2),
        agent_return_pct=round(agent_return * 100, 2),
        benchmark_return_pct=round(bench_return * 100, 2),
    )


def compare_multi_agents(
    engine_result,
    initial_cash: Decimal,
    benchmark_curve: list[tuple[date, Decimal]] | None = None,
) -> MultiAgentComparison:
    """Compare multiple agents from a single engine run."""
    comparison = MultiAgentComparison()

    for agent_id, data in engine_result.agent_data.items():
        comparison.agents.append(agent_id)
        equity_curve = data.get("equity_curve", [])
        trades = data.get("trades", [])

        metrics = calculate_metrics(equity_curve, initial_cash, trades)
        comparison.metrics[agent_id] = metrics

        if benchmark_curve:
            vs = compare_vs_benchmark(equity_curve, benchmark_curve, initial_cash)
            comparison.vs_benchmark[agent_id] = vs

    comparison.rank_by("sharpe_ratio")
    return comparison


def _daily_returns(curve: list[tuple[date, Decimal]]) -> dict[date, float]:
    returns = {}
    for index in range(1, len(curve)):
        previous = float(curve[index - 1][1])
        if previous != 0:
            returns[curve[index][0]] = (float(curve[index][1]) - previous) / previous
    return returns
