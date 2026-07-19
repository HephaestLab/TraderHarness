"""Shared conversion from EngineResult to persisted API/CLI result documents."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from traderharness.core.engine import EngineResult
from traderharness.metrics.behavior import calculate_behavior
from traderharness.metrics.comparison import compare_vs_benchmark
from traderharness.metrics.performance import calculate_metrics


def build_result_document(
    result: EngineResult,
    *,
    initial_cash: Decimal,
    config: dict[str, Any],
    benchmark_curve: list | None = None,
    entity_masker=None,
) -> dict[str, Any]:
    """Build the canonical persisted result shared by CLI and web runs."""
    agents: dict[str, Any] = {}
    for agent_id, data in result.agent_data.items():
        metrics = calculate_metrics(data["equity_curve"], initial_cash, data["trades"])
        steps = (data.get("trajectory") or {}).get("steps", [])
        counts = Counter(step.get("date") for step in steps if step.get("type") == "tool_call")
        tool_calls = [counts.get(str(day), 0) for day, _ in data["equity_curve"]]
        behavior = asdict(
            calculate_behavior(
                data["trades"],
                data["equity_curve"],
                initial_cash,
                tool_calls,
            )
        )
        trades = data["trades"]
        if entity_masker is not None:
            trades = entity_masker.mask_obj(trades)
            behavior = entity_masker.mask_obj(behavior)
        comparison = (
            compare_vs_benchmark(data["equity_curve"], benchmark_curve, initial_cash)
            if benchmark_curve
            else None
        )
        agents[agent_id] = {
            "equity_curve": [(str(day), float(value)) for day, value in data["equity_curve"]],
            "trades": trades,
            "trajectory": data.get("trajectory"),
            "behavior": behavior,
            "vs_benchmark": asdict(comparison) if comparison else None,
            "metrics": asdict(metrics),
        }

    return {
        "trading_days": result.trading_days,
        "start_date": str(result.start_date),
        "end_date": str(result.end_date),
        "config": config,
        "agent_data": agents,
        "benchmark": (
            {
                "name": "CSI 300",
                "equity_curve": [(str(day), float(value)) for day, value in benchmark_curve],
            }
            if benchmark_curve
            else None
        ),
    }
