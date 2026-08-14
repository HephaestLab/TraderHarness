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

    def _trade_date(trade: dict) -> date | None:
        value = trade.get("date") or trade.get("trade_date")
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value if isinstance(value, date) else None

    curve_dates = [day for day, _ in equity_curve]
    day_index = {day: index for index, day in enumerate(curve_dates)}
    quantities: dict[str, int] = {}
    opened_on: dict[str, date] = {}
    holding_days_list: list[int] = []
    for trade in sorted(
        trades,
        key=lambda item: (day_index.get(_trade_date(item), 10**9), _trade_date(item) or date.max),
    ):
        code = str(trade.get("stock_code", ""))
        trade_date = _trade_date(trade)
        if not code or trade_date is None:
            continue
        quantity = max(0, int(trade.get("quantity", 0) or 0))
        current = quantities.get(code, 0)
        if trade.get("action") == "buy":
            if current == 0:
                opened_on[code] = trade_date
            quantities[code] = current + (quantity or 1)
        elif trade.get("action") == "sell" and current > 0:
            remaining = 0 if quantity == 0 else max(0, current - quantity)
            quantities[code] = remaining
            if remaining == 0 and code in opened_on:
                opened = opened_on.pop(code)
                if opened in day_index and trade_date in day_index:
                    days = day_index[trade_date] - day_index[opened]
                else:
                    days = (trade_date - opened).days
                if days >= 0:
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

    buy_count = sum(1 for t in trades if t.get("action") == "buy")
    sell_count = sum(1 for t in trades if t.get("action") == "sell")

    # End-of-day empty state reconstructed from actual fills. Equity being near
    # initial cash says nothing about whether a position is open.
    empty_days = 0
    if equity_curve:
        trades_by_date: dict[date, list[dict]] = {}
        for trade in trades:
            trade_date = _trade_date(trade)
            if trade_date is not None:
                trades_by_date.setdefault(trade_date, []).append(trade)
        end_quantities: dict[str, int] = {}
        for day, _ in equity_curve:
            for trade in trades_by_date.get(day, []):
                code = str(trade.get("stock_code", ""))
                quantity = max(0, int(trade.get("quantity", 0) or 0))
                if trade.get("action") == "buy":
                    end_quantities[code] = end_quantities.get(code, 0) + (quantity or 1)
                elif trade.get("action") == "sell":
                    current = end_quantities.get(code, 0)
                    end_quantities[code] = 0 if quantity == 0 else max(0, current - quantity)
            if not any(quantity > 0 for quantity in end_quantities.values()):
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
