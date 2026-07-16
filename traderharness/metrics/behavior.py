"""Behavior metrics — analyze agent trading behavior from trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class BehaviorMetrics:
    avg_tool_calls_per_day: float
    avg_holding_days: float
    max_single_position_pct: float
    empty_days_pct: float
    total_buy_count: int
    total_sell_count: int
    avg_trade_size_pct: float
    most_traded_stocks: list[tuple[str, int]]


def calculate_behavior(
    trades: list[dict],
    equity_curve: list[tuple[date, Decimal]],
    initial_cash: Decimal,
    tool_call_counts: list[int] | None = None,
) -> BehaviorMetrics:
    """Calculate agent behavior metrics from trade history."""
    trading_days = len(equity_curve) if equity_curve else 1

    # Tool calls per day
    avg_tools = 0.0
    if tool_call_counts:
        avg_tools = sum(tool_call_counts) / len(tool_call_counts)

    # Holding days: compute average time between buy and sell for same stock
    buy_dates: dict[str, list[date]] = {}
    sell_dates: dict[str, list[date]] = {}
    for t in trades:
        code = t.get("stock_code", "")
        trade_date = t.get("date") or t.get("trade_date")
        if isinstance(trade_date, str):
            trade_date = date.fromisoformat(trade_date)
        if t.get("action") == "buy":
            buy_dates.setdefault(code, []).append(trade_date)
        elif t.get("action") == "sell":
            sell_dates.setdefault(code, []).append(trade_date)

    holding_days_list = []
    for code in sell_dates:
        buys = sorted(buy_dates.get(code, []))
        sells = sorted(sell_dates[code])
        for i, sell_d in enumerate(sells):
            if i < len(buys):
                days = (sell_d - buys[i]).days
                if days > 0:
                    holding_days_list.append(days)

    avg_holding = sum(holding_days_list) / len(holding_days_list) if holding_days_list else 0.0

    # Max single position percentage
    max_pos_pct = 0.0
    if equity_curve:
        # Approximate from trades
        for t in trades:
            if t.get("action") == "buy":
                amount = float(t.get("amount", 0) or t.get("total_cost", 0))
                equity_val = float(initial_cash)
                if equity_curve:
                    # Find closest equity
                    trade_date = t.get("date") or t.get("trade_date")
                    if isinstance(trade_date, str):
                        trade_date = date.fromisoformat(trade_date)
                    for d, v in equity_curve:
                        if d <= trade_date:
                            equity_val = float(v)
                if equity_val > 0:
                    pct = amount / equity_val * 100
                    max_pos_pct = max(max_pos_pct, pct)

    # Empty days: days with no positions
    # Approximate: days where no buy was active
    buy_count = sum(1 for t in trades if t.get("action") == "buy")
    sell_count = sum(1 for t in trades if t.get("action") == "sell")

    # If we have equity curve, count days near initial cash as empty
    empty_days = 0
    if equity_curve:
        init_val = float(initial_cash)
        for _, v in equity_curve:
            if abs(float(v) - init_val) / init_val < 0.001:
                empty_days += 1
    empty_pct = (empty_days / trading_days * 100) if trading_days > 0 else 0.0

    # Average trade size
    trade_amounts = [float(t.get("amount", 0)) for t in trades if t.get("amount")]
    avg_trade_size = 0.0
    if trade_amounts and float(initial_cash) > 0:
        avg_trade_size = (sum(trade_amounts) / len(trade_amounts)) / float(initial_cash) * 100

    # Most traded stocks
    stock_counts: dict[str, int] = {}
    for t in trades:
        code = t.get("stock_code", "")
        stock_counts[code] = stock_counts.get(code, 0) + 1
    most_traded = sorted(stock_counts.items(), key=lambda x: -x[1])[:5]

    return BehaviorMetrics(
        avg_tool_calls_per_day=round(avg_tools, 1),
        avg_holding_days=round(avg_holding, 1),
        max_single_position_pct=round(max_pos_pct, 1),
        empty_days_pct=round(empty_pct, 1),
        total_buy_count=buy_count,
        total_sell_count=sell_count,
        avg_trade_size_pct=round(avg_trade_size, 1),
        most_traded_stocks=most_traded,
    )
