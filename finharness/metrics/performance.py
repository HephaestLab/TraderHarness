"""Performance metrics — Sharpe, Calmar, Sortino, drawdown, win rate, etc."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

RISK_FREE_RATE = 0.025


@dataclass
class PerformanceMetrics:
    total_return_pct: float
    annual_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_consecutive_loss_days: int
    win_rate: float
    profit_loss_ratio: float
    turnover_rate: float
    total_trades: int
    trading_days: int
    final_value: float


def calculate_metrics(
    equity_curve: list[tuple[date, Decimal]],
    initial_cash: Decimal,
    trades: list[dict],
) -> PerformanceMetrics:
    if not equity_curve:
        return PerformanceMetrics(
            total_return_pct=0.0, annual_return_pct=0.0,
            sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
            max_drawdown_pct=0.0, max_consecutive_loss_days=0,
            win_rate=0.0, profit_loss_ratio=0.0, turnover_rate=0.0,
            total_trades=0, trading_days=0, final_value=float(initial_cash),
        )

    values = [float(v) for _, v in equity_curve]
    initial = float(initial_cash)
    final = values[-1]
    trading_days = len(equity_curve)

    total_return_pct = ((final - initial) / initial * 100) if initial else 0.0

    days_span = (equity_curve[-1][0] - equity_curve[0][0]).days
    if days_span > 0:
        annual_return_pct = ((1 + (final - initial) / initial) ** (365 / days_span) - 1) * 100
    else:
        annual_return_pct = 0.0

    daily_returns = []
    for i in range(1, len(values)):
        if values[i - 1] != 0:
            daily_returns.append((values[i] - values[i - 1]) / values[i - 1])

    sharpe_ratio = _calc_sharpe(daily_returns, annual_return_pct)
    sortino_ratio = _calc_sortino(daily_returns, annual_return_pct)
    max_drawdown_pct = _calc_max_drawdown(values) * 100
    calmar_ratio = (annual_return_pct / 100) / (max_drawdown_pct / 100) if max_drawdown_pct > 0 else 0.0
    max_consecutive_loss_days = _calc_max_consecutive_loss(daily_returns)
    win_rate, profit_loss_ratio, total_trades = _calc_trade_stats(trades)
    turnover_rate = _calc_turnover(trades, initial, trading_days)

    return PerformanceMetrics(
        total_return_pct=round(total_return_pct, 2),
        annual_return_pct=round(annual_return_pct, 2),
        sharpe_ratio=round(sharpe_ratio, 2),
        sortino_ratio=round(sortino_ratio, 2),
        calmar_ratio=round(calmar_ratio, 2),
        max_drawdown_pct=round(max_drawdown_pct, 2),
        max_consecutive_loss_days=max_consecutive_loss_days,
        win_rate=round(win_rate * 100, 1),
        profit_loss_ratio=round(profit_loss_ratio, 2),
        turnover_rate=round(turnover_rate, 2),
        total_trades=total_trades,
        trading_days=trading_days,
        final_value=round(final, 2),
    )


def _calc_sharpe(daily_returns: list[float], annual_return_pct: float) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean_r = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    annual_vol = math.sqrt(variance) * math.sqrt(252)
    return (annual_return_pct / 100 - RISK_FREE_RATE) / annual_vol if annual_vol else 0.0


def _calc_sortino(daily_returns: list[float], annual_return_pct: float) -> float:
    if len(daily_returns) < 2:
        return 0.0
    downside = [r for r in daily_returns if r < 0]
    if not downside:
        return 0.0
    downside_var = sum(r ** 2 for r in downside) / len(downside)
    downside_vol = math.sqrt(downside_var) * math.sqrt(252)
    return (annual_return_pct / 100 - RISK_FREE_RATE) / downside_vol if downside_vol else 0.0


def _calc_max_drawdown(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _calc_max_consecutive_loss(daily_returns: list[float]) -> int:
    max_loss = 0
    current = 0
    for r in daily_returns:
        if r < 0:
            current += 1
            max_loss = max(max_loss, current)
        else:
            current = 0
    return max_loss


def _calc_trade_stats(trades: list[dict]) -> tuple[float, float, int]:
    sell_trades = [t for t in trades if t.get("action") == "sell"]
    if not sell_trades:
        return 0.0, 0.0, 0
    profits, losses = [], []
    counted = 0
    for t in sell_trades:
        pnl = t.get("pnl")
        if pnl is None:
            if "buy_cost" in t:
                pnl = float(t.get("net_income", 0)) - float(t["buy_cost"])
            else:
                continue
        else:
            pnl = float(pnl)
        counted += 1
        if pnl > 0:
            profits.append(pnl)
        elif pnl < 0:
            losses.append(abs(pnl))
    win_rate = len(profits) / counted if counted else 0.0
    avg_profit = sum(profits) / len(profits) if profits else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    plr = avg_profit / avg_loss if avg_loss else 0.0
    return win_rate, plr, counted


def _calc_turnover(trades: list[dict], initial_value: float, trading_days: int) -> float:
    if trading_days == 0 or initial_value == 0:
        return 0.0
    total_volume = sum(float(t.get("amount", 0)) for t in trades)
    return total_volume / initial_value / trading_days * 252
