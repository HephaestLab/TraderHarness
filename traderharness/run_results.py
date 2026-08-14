"""Shared conversion from EngineResult to persisted API/CLI result documents."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from traderharness.core.engine import EngineResult
from traderharness.core.masking import DateMasker
from traderharness.metrics.behavior import calculate_behavior
from traderharness.metrics.comparison import compare_vs_benchmark
from traderharness.metrics.performance import calculate_metrics

_DATE_METADATA_KEYS = {
    "date",
    "trade_date",
    "start_date",
    "end_date",
    "completed_at",
    "created_at",
    "generated_at",
    "equity_curve",
}


def _mask_agent_visible_dates(value, masker: DateMasker):
    """Mask prose payloads without breaking result timeline metadata."""
    if isinstance(value, str):
        return masker.mask_text(value)
    if isinstance(value, dict):
        return {
            key: item
            if key in _DATE_METADATA_KEYS
            else _mask_agent_visible_dates(item, masker)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_agent_visible_dates(item, masker) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_agent_visible_dates(item, masker) for item in value)
    return value


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
    total_usage = Counter()
    date_masker = DateMasker(
        anchor=result.end_date,
        enabled=bool(config.get("mask_dates", False)),
    )
    for agent_id, data in result.agent_data.items():
        metrics = calculate_metrics(data["equity_curve"], initial_cash, data["trades"])
        steps = (data.get("trajectory") or {}).get("steps", [])
        usage = Counter()
        for step in steps:
            if step.get("type") != "llm_exchange":
                continue
            exchange = (step.get("data") or {}).get("response") or {}
            raw_usage = exchange.get("_usage") or {}
            usage.update(
                {
                    "llm_prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
                    "llm_completion_tokens": int(raw_usage.get("completion_tokens") or 0),
                    "llm_total_tokens": int(raw_usage.get("total_tokens") or 0),
                    "llm_exchanges": 1,
                }
            )
        counts = Counter(step.get("date") for step in steps if step.get("type") == "tool_call")
        tool_calls = [counts.get(str(day), 0) for day, _ in data["equity_curve"]]
        usage["tool_calls"] = sum(tool_calls)
        total_usage.update(usage)
        behavior = asdict(
            calculate_behavior(
                data["trades"],
                data["equity_curve"],
                initial_cash,
                tool_calls,
            )
        )
        trades = data["trades"]
        conditional_orders = data.get("conditional_orders", [])
        conditional_order_events = data.get("conditional_order_events", [])
        memory_events = data.get("memory_events", [])
        trajectory = data.get("trajectory")
        if date_masker.enabled:
            memory_events = _mask_agent_visible_dates(memory_events, date_masker)
            trajectory = _mask_agent_visible_dates(trajectory, date_masker)
        if entity_masker is not None:
            trades = entity_masker.mask_obj(trades)
            behavior = entity_masker.mask_obj(behavior)
            conditional_orders = entity_masker.mask_obj(conditional_orders)
            conditional_order_events = entity_masker.mask_obj(conditional_order_events)
            memory_events = entity_masker.mask_obj(memory_events)
            memory_events = entity_masker.sanitize_agent_obj(memory_events)
            trajectory = entity_masker.sanitize_agent_obj(trajectory)
        comparison = (
            compare_vs_benchmark(data["equity_curve"], benchmark_curve, initial_cash)
            if benchmark_curve
            else None
        )
        agents[agent_id] = {
            "equity_curve": [(str(day), float(value)) for day, value in data["equity_curve"]],
            "trades": trades,
            "conditional_orders": conditional_orders,
            "conditional_order_events": conditional_order_events,
            "memory_events": memory_events,
            "trajectory": trajectory,
            "behavior": behavior,
            "vs_benchmark": asdict(comparison) if comparison else None,
            "metrics": asdict(metrics),
            "usage": dict(usage),
        }

    return {
        "trading_days": result.trading_days,
        "start_date": str(result.start_date),
        "end_date": str(result.end_date),
        "config": config,
        "usage": dict(total_usage),
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
