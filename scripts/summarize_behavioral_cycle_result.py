"""Print a compact, reproducible audit summary for a TraderHarness result."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any


def _trade_date(trade: dict[str, Any]) -> str:
    return str(trade.get("trade_date") or trade.get("date") or "")


def _weighted_median(samples: list[tuple[int, int]]) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    midpoint = sum(weight for _, weight in ordered) / 2
    cumulative = 0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return float(value)
    return float(ordered[-1][0])


def _is_tool_error(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("error")) or result.get("success") is False
    if not isinstance(result, str):
        return False
    lowered = result.lower()
    return any(token in lowered for token in ("error", "traceback", "错误", "失败"))


def summarize(path: Path, agent_id: str | None = None) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if agent_id is None:
        agent_id = next(iter(result["agent_data"]))
    agent = result["agent_data"][agent_id]
    trades = agent["trades"]
    steps = agent["trajectory"]["steps"]
    agent_curve = {day: float(value) for day, value in agent["equity_curve"]}
    trading_dates = list(agent_curve)
    day_indexes = {day: index for index, day in enumerate(trading_dates)}

    tool_steps = [
        step
        for step in steps
        if step.get("type") == "tool_call" and step.get("data", {}).get("name")
    ]
    tool_counts = Counter(step["data"]["name"] for step in tool_steps)
    tool_errors = Counter(
        step["data"]["name"]
        for step in tool_steps
        if _is_tool_error(step["data"].get("result"))
    )
    usage = Counter()
    for step in steps:
        if step.get("type") != "llm_exchange":
            continue
        exchange_usage = step.get("data", {}).get("response", {}).get("_usage", {})
        usage.update(
            {
                key: value
                for key, value in exchange_usage.items()
                if isinstance(value, (int, float))
            }
        )

    feature_steps = [
        step
        for step in tool_steps
        if step["data"]["name"] == "execute_code"
        and "get_behavioral_features" in str(step["data"].get("args", {}).get("code", ""))
    ]
    order_steps = [step for step in tool_steps if step["data"]["name"] == "place_order"]
    order_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for step in order_steps:
        args = step["data"].get("args", {})
        order_groups[(str(step.get("date", "")), str(args.get("stock_code", "")))].append(step)
    duplicate_order_groups = []
    for (day, code), grouped in sorted(order_groups.items()):
        if len(grouped) < 2:
            continue
        duplicate_order_groups.append(
            {
                "date": day,
                "stock_code": code,
                "attempts": len(grouped),
                "successful": sum(
                    step["data"].get("result", {}).get("success") is True
                    for step in grouped
                    if isinstance(step["data"].get("result"), dict)
                ),
            }
        )

    quantities: defaultdict[str, int] = defaultdict(int)
    costs: defaultdict[str, Decimal] = defaultdict(Decimal)
    fifo_lots: defaultdict[str, list[list[int]]] = defaultdict(list)
    holding_samples: list[tuple[int, int]] = []
    sell_holding_details: list[dict[str, Any]] = []
    pnl_by_code: defaultdict[str, Decimal] = defaultdict(Decimal)
    pnl_by_month: defaultdict[str, Decimal] = defaultdict(Decimal)
    downward_adds: list[dict[str, Any]] = []
    first_entries: list[dict[str, Any]] = []
    peak_positions = 0
    peak_cost_exposure = Decimal(0)
    positive_sells = 0
    negative_sells = 0

    for trade in trades:
        code = trade["stock_code"]
        day = _trade_date(trade)
        quantity = int(trade["quantity"])
        price = Decimal(str(trade["price"]))
        amount = Decimal(str(trade.get("amount", price * quantity)))
        if trade["action"] == "buy":
            if quantities[code] and price < costs[code] / quantities[code]:
                downward_adds.append(
                    {
                        "date": day,
                        "stock_code": code,
                        "price": float(price),
                        "prior_avg_cost": round(float(costs[code] / quantities[code]), 4),
                    }
                )
            if quantities[code] == 0:
                equity = agent_curve.get(day)
                first_entries.append(
                    {
                        "date": day,
                        "stock_code": code,
                        "notional_pct": round(float(amount) / equity * 100, 2) if equity else None,
                    }
                )
            quantities[code] += quantity
            costs[code] += Decimal(str(trade.get("total_cost", amount)))
            fifo_lots[code].append([quantity, day_indexes.get(day, 0)])
        else:
            prior_quantity = quantities[code]
            if prior_quantity:
                average_cost = costs[code] / prior_quantity
                costs[code] -= average_cost * quantity
                quantities[code] -= quantity
                if quantities[code] == 0:
                    costs[code] = Decimal(0)
            remaining = quantity
            sell_index = day_indexes.get(day, 0)
            matched_holding: list[tuple[int, int]] = []
            while remaining > 0 and fifo_lots[code]:
                lot = fifo_lots[code][0]
                matched = min(remaining, lot[0])
                holding = max(0, sell_index - lot[1])
                holding_samples.append((holding, matched))
                matched_holding.append((holding, matched))
                lot[0] -= matched
                remaining -= matched
                if lot[0] == 0:
                    fifo_lots[code].pop(0)
            pnl = Decimal(str(trade.get("pnl", 0)))
            matched_quantity = sum(weight for _, weight in matched_holding)
            sell_holding_details.append(
                {
                    "date": day,
                    "stock_code": code,
                    "quantity": quantity,
                    "weighted_holding_trading_days": round(
                        sum(days * weight for days, weight in matched_holding)
                        / matched_quantity,
                        2,
                    )
                    if matched_quantity
                    else None,
                    "pnl": round(float(pnl), 2),
                    "reasoning": str(trade.get("signal_reasoning", "")),
                }
            )
            pnl_by_code[code] += pnl
            pnl_by_month[day[:7]] += pnl
            positive_sells += pnl > 0
            negative_sells += pnl < 0

        open_codes = [held_code for held_code, held in quantities.items() if held > 0]
        peak_positions = max(peak_positions, len(open_codes))
        peak_cost_exposure = max(
            peak_cost_exposure,
            sum((costs[held_code] for held_code in open_codes), Decimal(0)),
        )

    daily_snapshots: dict[str, dict[str, Any]] = {}
    invalid_snapshots: list[dict[str, Any]] = []
    for step in tool_steps:
        if step["data"]["name"] != "get_portfolio":
            continue
        snapshot = step["data"].get("result")
        if not isinstance(snapshot, dict) or not snapshot.get("total_value"):
            continue
        total = float(snapshot["total_value"])
        cash = float(snapshot.get("cash", 0))
        positions = snapshot.get("positions", [])
        market_value = sum(float(position.get("market_value", 0)) for position in positions)
        tolerance = max(1.0, abs(total) * 0.001)
        if abs(total - cash - market_value) > tolerance:
            invalid_snapshots.append(
                {
                    "date": step.get("date"),
                    "cash": cash,
                    "total_value": total,
                    "position_market_value": round(market_value, 2),
                }
            )
            continue
        exposure = market_value / total * 100
        max_single = max(
            (float(position.get("market_value", 0)) / total * 100 for position in positions),
            default=0.0,
        )
        daily_snapshots[str(step.get("date", ""))] = {
            "exposure": exposure,
            "max_single": max_single,
        }
    exposures = [snapshot["exposure"] for snapshot in daily_snapshots.values()]
    nonzero_exposures = [value for value in exposures if value > 0.01]
    max_single_exposure = max(
        (snapshot["max_single"] for snapshot in daily_snapshots.values()),
        default=0.0,
    )

    reasons = [str(trade.get("signal_reasoning", "")) for trade in trades]
    required_fields = {
        "stage": ("stage", "阶段"),
        "evidence": ("evidence", "证据", "支持"),
        "counterevidence": ("counter_evidence", "counterevidence", "反证"),
        "market": ("market_regime", "市场"),
        "position_or_risk": ("position_basis", "target_exposure", "仓位", "风险"),
        "invalidation": ("invalidation", "structural_stop", "失效", "止损"),
        "exit": ("exit_plan", "退出", "清仓", "减仓"),
    }
    reason_coverage = {
        field: {
            "count": sum(any(token in reason for token in tokens) for reason in reasons),
            "pct": round(
                100 * sum(any(token in reason for token in tokens) for reason in reasons) / len(reasons),
                1,
            )
            if reasons
            else 0.0,
        }
        for field, tokens in required_fields.items()
    }

    total_closed_quantity = sum(weight for _, weight in holding_samples)
    weighted_holding = (
        sum(days * weight for days, weight in holding_samples) / total_closed_quantity
        if total_closed_quantity
        else None
    )
    top_realized = sorted(
        ((code, round(float(pnl), 2)) for code, pnl in pnl_by_code.items()),
        key=lambda item: (-item[1], item[0]),
    )
    open_positions = {
        code: quantity for code, quantity in sorted(quantities.items()) if quantity > 0
    }
    benchmark = result.get("benchmark", {})
    benchmark_curve = benchmark.get("equity_curve", [])
    initial_cash = float(result.get("config", {}).get("initial_cash", 1_000_000))
    benchmark_return = None
    if len(benchmark_curve) >= 2 and float(benchmark_curve[0][1]):
        benchmark_return = round(
            (float(benchmark_curve[-1][1]) / float(benchmark_curve[0][1]) - 1) * 100,
            2,
        )

    return {
        "artifact": str(path.resolve()),
        "agent_id": agent_id,
        "period": [result["start_date"], result["end_date"]],
        "trading_days": result["trading_days"],
        "metrics": agent["metrics"],
        "vs_benchmark": agent["vs_benchmark"],
        "behavior": agent["behavior"],
        "benchmark": {
            "name": benchmark.get("name"),
            "total_return_pct": benchmark_return,
            "final_value": float(benchmark_curve[-1][1]) if benchmark_curve else None,
        },
        "llm_total_tokens": result.get("usage", {}).get("llm_total_tokens"),
        "trajectory": {
            "steps": len(steps),
            "llm_exchanges": sum(step.get("type") == "llm_exchange" for step in steps),
            "tool_calls": len(tool_steps),
            "tool_counts": dict(tool_counts.most_common()),
            "llm_usage": dict(usage),
            "tool_errors": dict(tool_errors.most_common()),
            "behavioral_feature_calls": len(feature_steps),
            "behavioral_feature_dates": sorted({str(step.get("date")) for step in feature_steps}),
            "duplicate_order_attempt_groups": duplicate_order_groups,
        },
        "execution": {
            "buy_count": sum(trade["action"] == "buy" for trade in trades),
            "sell_count": sum(trade["action"] == "sell" for trade in trades),
            "positive_sells": positive_sells,
            "negative_sells": negative_sells,
            "realized_pnl": round(float(sum(pnl_by_code.values(), Decimal(0))), 2),
            "peak_concurrent_positions": peak_positions,
            "peak_acquisition_cost_exposure_pct_of_initial_cash": round(
                float(peak_cost_exposure) / initial_cash * 100, 2
            ),
            "downward_average_events": downward_adds,
            "first_entries": first_entries,
            "first_entries_below_25_pct": [
                entry for entry in first_entries if (entry["notional_pct"] or 0) < 25
            ],
            "open_positions_at_end": open_positions,
            "weighted_avg_holding_trading_days": round(weighted_holding, 2)
            if weighted_holding is not None
            else None,
            "weighted_median_holding_trading_days": _weighted_median(holding_samples),
            "sells_under_5_trading_days": [
                detail
                for detail in sell_holding_details
                if detail["weighted_holding_trading_days"] is not None
                and detail["weighted_holding_trading_days"] < 5
            ],
            "closed_quantity_under_5_days_pct": round(
                100
                * sum(weight for days, weight in holding_samples if days < 5)
                / total_closed_quantity,
                2,
            )
            if total_closed_quantity
            else None,
            "top_realized_pnl_by_canonical_code": top_realized[:10],
            "bottom_realized_pnl_by_canonical_code": top_realized[-10:],
            "realized_pnl_by_month": {
                month: round(float(pnl), 2) for month, pnl in sorted(pnl_by_month.items())
            },
        },
        "exposure": {
            "validated_daily_snapshots": len(exposures),
            "invalid_snapshot_count": len(invalid_snapshots),
            "invalid_snapshots": invalid_snapshots,
            "average_pct": round(sum(exposures) / len(exposures), 2) if exposures else None,
            "median_pct": round(median(exposures), 2) if exposures else None,
            "peak_pct": round(max(exposures), 2) if exposures else None,
            "zero_days_pct": round(
                100 * sum(value <= 0.01 for value in exposures) / len(exposures), 2
            )
            if exposures
            else None,
            "nonzero_average_pct": round(
                sum(nonzero_exposures) / len(nonzero_exposures), 2
            )
            if nonzero_exposures
            else None,
            "max_single_position_pct": round(max_single_exposure, 2),
        },
        "reason_field_coverage": reason_coverage,
        "generated_on": date.today().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--agent-id")
    args = parser.parse_args()
    print(json.dumps(summarize(args.result, args.agent_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
