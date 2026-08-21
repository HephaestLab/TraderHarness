"""分析工具 — screen_stocks, get_market_overview, get_sector_summary。"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from traderharness.data.stock_registry_loader import get_stock_industry
from traderharness.tools._coerce import safe_int
from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition

logger = logging.getLogger(__name__)


def _horizon_change(close: np.ndarray, sessions: int) -> float | None:
    """Latest close return over N completed sessions, or None when unavailable."""
    if len(close) <= sessions:
        return None
    start = float(close[-sessions - 1])
    end = float(close[-1])
    if start <= 0 or not math.isfinite(start) or not math.isfinite(end):
        return None
    return (end / start - 1.0) * 100.0


def _stock_leadership_metrics(filtered: pd.DataFrame, code: str) -> dict | None:
    """Return raw multi-horizon evidence used for sector and leader comparison."""
    if len(filtered) < 2 or "close" not in filtered.columns:
        return None
    close = pd.to_numeric(filtered["close"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(close).all() or float(close[-1]) <= 0:
        return None
    change_1d = _horizon_change(close, 1)
    if change_1d is None:
        return None

    volume_ratio = None
    if "volume" in filtered.columns and len(filtered) >= 20:
        volume = pd.to_numeric(filtered["volume"], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(volume[-20:]).all():
            baseline = float(np.mean(volume[-20:]))
            if baseline > 0:
                volume_ratio = float(np.mean(volume[-5:])) / baseline

    amount_1d = None
    amount_5d = None
    amount_20d = None
    if "amount" in filtered.columns:
        amount = pd.to_numeric(filtered["amount"], errors="coerce").to_numpy(dtype=float)
        if len(amount) and math.isfinite(float(amount[-1])):
            amount_1d = float(amount[-1]) / 1_000_000
        if len(amount) >= 5 and np.isfinite(amount[-5:]).all():
            amount_5d = float(np.mean(amount[-5:])) / 1_000_000
        if len(amount) >= 20 and np.isfinite(amount[-20:]).all():
            amount_20d = float(np.mean(amount[-20:])) / 1_000_000

    distance_from_20d_high = None
    if "high" in filtered.columns and len(filtered) >= 20:
        high = pd.to_numeric(filtered["high"], errors="coerce").to_numpy(dtype=float)
        recent_high = float(np.nanmax(high[-20:]))
        if math.isfinite(recent_high) and recent_high > 0:
            distance_from_20d_high = (float(close[-1]) / recent_high - 1.0) * 100.0

    change_5d = _horizon_change(close, 5)
    change_20d = _horizon_change(close, 20)
    return {
        "code": code,
        "close": round(float(close[-1]), 2),
        # Backward-compatible name used by existing clients.
        "change_pct": round(float(change_1d), 2),
        "change_1d_pct": round(float(change_1d), 2),
        "change_5d_pct": round(float(change_5d), 2) if change_5d is not None else None,
        "change_20d_pct": round(float(change_20d), 2) if change_20d is not None else None,
        "volume_5_to_20": round(float(volume_ratio), 3) if volume_ratio is not None else None,
        "amount_1d_million": _rounded_or_none(amount_1d),
        "amount_5d_avg_million": _rounded_or_none(amount_5d),
        "amount_20d_avg_million": _rounded_or_none(amount_20d),
        "distance_from_20d_high_pct": (
            round(float(distance_from_20d_high), 2) if distance_from_20d_high is not None else None
        ),
    }


def _mean_present(rows: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _positive_ratio(rows: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(value > 0 for value in values) / len(values) * 100.0 if values else None


def _rounded_or_none(value: float | None, digits: int = 2) -> float | None:
    return round(float(value), digits) if value is not None and math.isfinite(value) else None


def _sector_metrics(sector: str, rows: list[dict]) -> dict:
    change_1d = _mean_present(rows, "change_1d_pct")
    return {
        "sector": sector,
        "stock_count": len(rows),
        # Backward-compatible name used by the current UI and prompt.
        "avg_change_pct": _rounded_or_none(change_1d),
        "change_1d_pct": _rounded_or_none(change_1d),
        "change_5d_pct": _rounded_or_none(_mean_present(rows, "change_5d_pct")),
        "change_20d_pct": _rounded_or_none(_mean_present(rows, "change_20d_pct")),
        "up_ratio_1d_pct": _rounded_or_none(_positive_ratio(rows, "change_1d_pct")),
        "up_ratio_5d_pct": _rounded_or_none(_positive_ratio(rows, "change_5d_pct")),
        "up_ratio_20d_pct": _rounded_or_none(_positive_ratio(rows, "change_20d_pct")),
    }


def _metric(row: dict, key: str, default: float = -math.inf) -> float:
    value = row.get(key)
    return float(value) if value is not None else default


def build_narrative_market_overview(ctx: ToolContext) -> dict:
    """Point-in-time multi-horizon market evidence for narrative agents."""
    sector_data: dict[str, list[dict]] = {}
    total_up = 0
    total_down = 0

    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        metrics = _stock_leadership_metrics(filtered.tail(120), code)
        if metrics is None:
            continue
        change = float(metrics["change_1d_pct"])
        if change > 0:
            total_up += 1
        elif change < 0:
            total_down += 1

        industry = get_stock_industry(code)
        sector_data.setdefault(industry, []).append(metrics)

    if not sector_data:
        return {"error": "当前交易日无市场数据"}

    sector_rows = [_sector_metrics(sector, rows) for sector, rows in sector_data.items() if len(rows) >= 3]
    strongest = sorted(
        sector_rows,
        key=lambda row: (
            -_metric(row, "change_5d_pct"),
            -_metric(row, "change_20d_pct"),
            -_metric(row, "up_ratio_5d_pct"),
            -_metric(row, "change_1d_pct"),
            row["sector"],
        ),
    )
    weakest = sorted(
        sector_rows,
        key=lambda row: (
            _metric(row, "change_20d_pct", math.inf),
            _metric(row, "change_5d_pct", math.inf),
            _metric(row, "change_1d_pct", math.inf),
            row["sector"],
        ),
    )
    rotation = [
        row
        for row in sector_rows
        if _metric(row, "change_20d_pct", math.inf) <= 0
        and _metric(row, "change_5d_pct") > 0
        and _metric(row, "change_1d_pct") > 0
        and _metric(row, "up_ratio_1d_pct") >= 50
    ]
    rotation.sort(
        key=lambda row: (
            -_metric(row, "up_ratio_1d_pct"),
            -_metric(row, "change_5d_pct"),
            -_metric(row, "change_1d_pct"),
            row["sector"],
        )
    )

    return {
        "total_stocks": total_up + total_down,
        "up_count": total_up,
        "down_count": total_down,
        "top_sectors": strongest[:5],
        "bottom_sectors": weakest[:5],
        "rotation_candidates": rotation[:5],
        "total_sectors": len(sector_rows),
        "ranking_rule": "top sectors rank by 5d, 20d, 5d breadth, then 1d strength",
        "rotation_candidate_rule": (
            "20d sector return <= 0, 5d and 1d returns > 0, 1d advancing breadth >= 50%; "
            "text catalyst is still required"
        ),
    }


def build_screen_stocks(ctx: ToolContext, params: dict | None = None) -> dict:
    """Point-in-time stock screen shared by tools and sandbox MarketAPI."""
    params = params or {}
    price_min = params.get("price_min", 0)
    price_max = params.get("price_max", 99999)
    change_pct_min = params.get("change_pct_min")
    change_pct_max = params.get("change_pct_max")
    volume_min = params.get("volume_min", 0)
    industry = params.get("industry", "")
    sort_by = params.get("sort_by", "change_5d")
    max_results = max(1, min(safe_int(params.get("max_results", 10), default=10), 30))

    if price_min > price_max:
        return {
            "success": False,
            "error": "price_min 不能大于 price_max",
            "error_code": "invalid_filter_range",
            "retryable": True,
            "correction": {
                "instruction": "交换或修正 price_min/price_max 后重试。",
                "price_min": price_min,
                "price_max": price_max,
            },
        }

    results = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 5:
            continue

        if industry:
            stock_industry = get_stock_industry(code)
            if industry not in stock_industry:
                continue

        last = filtered.iloc[-1]
        close = float(last["close"])
        volume = safe_int(last.get("volume", 0))

        if close < price_min or close > price_max:
            continue
        if volume < volume_min:
            continue

        prev = filtered.iloc[-2]
        prev_close = float(prev["close"])
        change_1d = ((close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0

        if change_pct_min is not None and change_1d < change_pct_min:
            continue
        if change_pct_max is not None and change_1d > change_pct_max:
            continue

        prev_5 = filtered.iloc[-5]
        change_5d = (close - float(prev_5["close"])) / float(prev_5["close"]) * 100

        results.append(
            {
                "code": code,
                "close": round(close, 2),
                "change_1d_pct": round(change_1d, 2),
                "change_5d_pct": round(change_5d, 2),
                "volume": volume,
            }
        )

    sort_key = {"change_5d": "change_5d_pct", "change_1d": "change_1d_pct", "volume": "volume"}.get(
        sort_by, "change_5d_pct"
    )
    results.sort(key=lambda x: (-x[sort_key], x["code"]))

    if not results:
        return {"stocks": [], "total_matched": 0, "hint": "无股票满足筛选条件，建议放宽条件"}

    return {"stocks": results[:max_results], "total_matched": len(results)}


def _finite_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return a finite ratio without emitting divide-by-zero warnings."""
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return default
    if abs(denominator) <= 1e-12:
        return default
    value = numerator / denominator
    return value if math.isfinite(value) else default


def build_behavioral_cycle_features(ctx: ToolContext) -> dict:
    """Return unlabeled point-in-time price/volume features for sandbox research.

    Indicator formulas remain deterministic and audited here.  The LLM is
    deliberately responsible for combining/ranking them in ``execute_code``;
    this function does not emit a stage or composite score.
    """
    sample_size = 0
    eligible_size = 0
    features: list[dict] = []
    required = ["open", "high", "low", "close", "volume"]

    for code, source in ctx.preloaded_daily.items():
        if source.empty or "date" not in source.columns:
            continue
        sample_size += 1
        frame = source.loc[source["date"] < ctx.current_date].tail(120).copy()
        if len(frame) < 60 or any(column not in frame.columns for column in required):
            continue
        for column in required:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
        frame = frame[
            (frame["close"] > 0)
            & (frame["high"] > 0)
            & (frame["low"] > 0)
            & (frame["volume"] >= 0)
            & (frame["high"] >= frame["low"])
        ]
        if len(frame) < 60:
            continue
        eligible_size += 1

        close = frame["close"].to_numpy(dtype=float)
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        volume = frame["volume"].to_numpy(dtype=float)
        previous_close = np.concatenate(([close[0]], close[:-1]))
        true_range = np.maximum.reduce((high - low, np.abs(high - previous_close), np.abs(low - previous_close)))

        last_close = float(close[-1])
        high_60 = float(np.max(high[-60:]))
        low_60 = float(np.min(low[-60:]))
        high_120 = float(np.max(high))
        resistance_20 = float(np.max(high[-21:-1]))
        support_20 = float(np.min(low[-21:-1]))
        atr_20 = float(np.mean(true_range[-20:]))
        atr_5 = float(np.mean(true_range[-5:]))
        volume_20 = float(np.mean(volume[-20:]))
        volume_5 = float(np.mean(volume[-5:]))

        spread = high - low
        clv = np.zeros_like(close, dtype=float)
        np.divide(2 * close - high - low, spread, out=clv, where=spread > 1e-12)
        returns = np.diff(close, prepend=close[0])
        up_volume = float(np.sum(volume[-20:][returns[-20:] > 0]))
        down_volume = float(np.sum(volume[-20:][returns[-20:] < 0]))
        signed_volume = np.sign(returns) * volume

        range_position_60 = _finite_ratio(last_close - low_60, high_60 - low_60, 0.5)
        drawdown_120_pct = (_finite_ratio(last_close, high_120, 1.0) - 1.0) * 100
        atr_pct = _finite_ratio(atr_20, last_close) * 100
        atr_contraction = _finite_ratio(atr_5, atr_20, 1.0)
        volume_ratio = _finite_ratio(volume_5, volume_20)
        up_down_volume_ratio = _finite_ratio(up_volume, down_volume, 1.0)
        obv_flow_20 = _finite_ratio(float(np.sum(signed_volume[-20:])), float(np.sum(volume[-20:])), 0.0)
        breakout_20_pct = (_finite_ratio(last_close, resistance_20, 1.0) - 1.0) * 100
        change_20_pct = (_finite_ratio(last_close, float(close[-20]), 1.0) - 1.0) * 100
        clv_5 = float(np.mean(clv[-5:]))
        clv_last = float(clv[-1])

        earlier_resistance = float(np.max(high[-26:-6]))
        recently_broke_out = float(np.max(close[-6:-1])) >= earlier_resistance * 1.005

        metrics = {
            "last_close": round(last_close, 3),
            "last_low": round(float(low[-1]), 3),
            "range_position_60": round(float(range_position_60), 4),
            "drawdown_120_pct": round(float(drawdown_120_pct), 2),
            "change_20_pct": round(float(change_20_pct), 2),
            "atr_20_pct": round(float(atr_pct), 3),
            "atr_5_to_20": round(float(atr_contraction), 3),
            "volume_5_to_20": round(float(volume_ratio), 3),
            "up_down_volume_ratio": round(float(up_down_volume_ratio), 3),
            "clv_5": round(float(clv_5), 3),
            "clv_last": round(float(clv_last), 3),
            "obv_flow_20": round(float(obv_flow_20), 3),
            "breakout_20d_pct": round(float(breakout_20_pct), 2),
            "support_20": round(float(support_20), 3),
            "resistance_20": round(float(resistance_20), 3),
            "earlier_resistance": round(float(earlier_resistance), 3),
            "observations": int(len(frame)),
        }
        if not all(math.isfinite(value) for value in metrics.values()):
            continue
        features.append(
            {
                "stock_code": code,
                **metrics,
                "touched_support": bool(float(low[-1]) <= support_20 * 1.01),
                "recently_broke_out": bool(recently_broke_out),
                "extended_20d": bool(change_20_pct >= 25),
                "distribution_risk": bool(range_position_60 >= 0.85 and volume_ratio >= 1.5 and clv_last < 0),
                "zero_volume_baseline": bool(volume_20 <= 0),
            }
        )

    features.sort(key=lambda row: row["stock_code"])
    return {
        "features": features,
        "sample_size": sample_size,
        "eligible_size": eligible_size,
        "as_of_rule": "strictly_before_current_date",
        "interpretation": "unlabeled observable features; stage and ranking are agent decisions",
    }


def build_behavioral_cycle_screen(ctx: ToolContext, max_results: int = 8) -> dict:
    """Deterministic baseline screen retained for benchmarks and regression tests."""
    max_results = max(1, min(safe_int(max_results, default=8), 20))
    feature_set = build_behavioral_cycle_features(ctx)
    candidates: list[dict] = []

    for row in feature_set["features"]:
        base_score = 0.0
        base_score += 1.5 if row["drawdown_120_pct"] <= -15 else 0.0
        base_score += 1.5 if row["range_position_60"] <= 0.45 else 0.0
        base_score += 1.0 if row["atr_5_to_20"] <= 0.9 else 0.0
        base_score += 1.0 if row["up_down_volume_ratio"] >= 1.1 else 0.0
        base_score += 1.0 if row["obv_flow_20"] > 0 else 0.0
        base_score += 0.5 if row["clv_5"] > 0 else 0.0

        is_markup = row["breakout_20d_pct"] >= 0.5 and row["volume_5_to_20"] >= 1.2 and row["clv_last"] >= 0.25
        is_test = (
            row["touched_support"]
            and row["last_close"] >= row["support_20"]
            and row["clv_last"] > 0
            and row["volume_5_to_20"] <= 1.05
        )
        is_washout = (
            row["recently_broke_out"]
            and row["last_close"] >= row["earlier_resistance"] * 0.98
            and row["volume_5_to_20"] <= 1.1
            and row["clv_last"] >= -0.2
        )

        if is_markup:
            stage = "markup"
            score = 8.0 + min(row["breakout_20d_pct"], 10.0) / 5.0 + min(row["volume_5_to_20"], 3.0) / 3.0
            invalidation = max(row["support_20"], row["resistance_20"] * 0.98)
        elif is_washout:
            stage = "washout"
            score = 6.0 + base_score
            invalidation = min(row["support_20"], row["earlier_resistance"] * 0.97)
        elif is_test:
            stage = "test"
            score = 5.0 + base_score
            invalidation = row["support_20"] * 0.98
        elif base_score >= 3.0:
            stage = "accumulation_candidate"
            score = base_score
            invalidation = row["support_20"] * 0.98
        else:
            continue

        risk_flags = []
        if row["extended_20d"]:
            risk_flags.append("extended_20d")
            score -= 1.5
        if row["distribution_risk"]:
            risk_flags.append("distribution_risk")
            score -= 2.0
        if row["zero_volume_baseline"]:
            risk_flags.append("zero_volume_baseline")
            score -= 2.0

        candidates.append(
            {
                "code": row["stock_code"],
                "stage": stage,
                "score": round(float(score), 3),
                **{
                    key: row[key]
                    for key in (
                        "range_position_60",
                        "drawdown_120_pct",
                        "change_20_pct",
                        "atr_20_pct",
                        "atr_5_to_20",
                        "volume_5_to_20",
                        "up_down_volume_ratio",
                        "clv_5",
                        "obv_flow_20",
                        "breakout_20d_pct",
                        "support_20",
                        "resistance_20",
                    )
                },
                "invalidation": round(float(invalidation), 3),
                "risk_flags": risk_flags,
            }
        )

    candidates.sort(key=lambda row: (-row["score"], row["code"]))
    return {
        "candidates": candidates[:max_results],
        "sample_size": feature_set["sample_size"],
        "eligible_size": feature_set["eligible_size"],
        "matched_size": len(candidates),
        "as_of_rule": "strictly_before_current_date",
        "interpretation": "stage labels are observable hypotheses, not operator intent",
    }


def build_narrative_sector_constituents(ctx: ToolContext, sector: str) -> list[dict] | dict:
    """Multi-horizon point-in-time constituents for a sector."""
    if not sector:
        return {"error": "请指定板块名称（如：电力设备、医药生物、金融行业）"}

    stocks = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        stock_industry = get_stock_industry(code)
        if sector not in stock_industry:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        metrics = _stock_leadership_metrics(filtered.tail(120), code)
        if metrics is not None:
            stocks.append(metrics)

    if not stocks:
        return {"error": f"未找到板块「{sector}」或该板块在当前日期无数据"}

    # Secondary key by code so equal change_pct ties stay fingerprint-stable.
    stocks.sort(key=lambda x: (-x["change_pct"], x["code"]))
    return stocks


def build_narrative_sector_summary(ctx: ToolContext, sector: str) -> dict:
    """Point-in-time multi-horizon sector and leader evidence."""
    stocks = build_narrative_sector_constituents(ctx, sector)
    if isinstance(stocks, dict):
        return stocks

    sector_metrics = _sector_metrics(sector, stocks)
    leaders = sorted(
        stocks,
        key=lambda row: (
            -_metric(row, "change_5d_pct"),
            -_metric(row, "change_20d_pct"),
            -_metric(row, "change_1d_pct"),
            -_metric(row, "volume_5_to_20"),
            row["code"],
        ),
    )
    return {
        **sector_metrics,
        "top_gainers": stocks[:5],
        "top_losers": stocks[-5:] if len(stocks) > 5 else [],
        "leaders": leaders[:5],
        "leader_ranking_rule": "5d, 20d, 1d relative strength, then 5d/20d volume ratio",
    }


def build_market_overview(ctx: ToolContext) -> dict:
    """Backward-compatible point-in-time market overview."""
    sector_data: dict[str, list[float]] = {}
    total_up = 0
    total_down = 0

    for code, df in ctx.preloaded_daily.items():
        if df.empty:
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2]
        prev_close = float(prev["close"])
        if prev_close == 0:
            continue
        change = (float(last["close"]) - prev_close) / prev_close * 100
        if change > 0:
            total_up += 1
        elif change < 0:
            total_down += 1

        industry = get_stock_industry(code)
        sector_data.setdefault(industry, []).append(change)

    if not sector_data:
        return {"error": "当前交易日无市场数据"}

    sector_avg = {sector: sum(values) / len(values) for sector, values in sector_data.items() if len(values) >= 3}
    sorted_sectors = sorted(sector_avg.items(), key=lambda item: -item[1])
    return {
        "total_stocks": total_up + total_down,
        "up_count": total_up,
        "down_count": total_down,
        "top_sectors": [
            {"sector": sector, "avg_change_pct": round(change, 2)} for sector, change in sorted_sectors[:5]
        ],
        "bottom_sectors": [
            {"sector": sector, "avg_change_pct": round(change, 2)} for sector, change in sorted_sectors[-5:]
        ],
        "total_sectors": len(sorted_sectors),
    }


def build_sector_constituents(ctx: ToolContext, sector: str) -> list[dict] | dict:
    """Backward-compatible point-in-time sector constituents."""
    if not sector:
        return {"error": "请指定板块名称（如：电力设备、医药生物、金融行业）"}

    stocks = []
    for code, df in ctx.preloaded_daily.items():
        if df.empty or sector not in get_stock_industry(code):
            continue
        filtered = df[df["date"] < ctx.current_date]
        if len(filtered) < 2:
            continue
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2]
        close = float(last["close"])
        prev_close = float(prev["close"])
        change = ((close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        stocks.append({"code": code, "close": round(close, 2), "change_pct": round(change, 2)})

    if not stocks:
        return {"error": f"未找到板块「{sector}」或该板块在当前日期无数据"}
    stocks.sort(key=lambda item: (-item["change_pct"], item["code"]))
    return stocks


def build_sector_summary(ctx: ToolContext, sector: str) -> dict:
    """Backward-compatible point-in-time sector summary."""
    stocks = build_sector_constituents(ctx, sector)
    if isinstance(stocks, dict):
        return stocks
    avg_change = sum(stock["change_pct"] for stock in stocks) / len(stocks)
    return {
        "sector": sector,
        "avg_change_pct": round(avg_change, 2),
        "stock_count": len(stocks),
        "top_gainers": stocks[:5],
        "top_losers": stocks[-5:] if len(stocks) > 5 else [],
    }


async def handle_get_market_overview(params: dict, ctx: ToolContext) -> dict:
    return build_market_overview(ctx)


async def handle_get_narrative_market_overview(params: dict, ctx: ToolContext) -> dict:
    cache_key = "_narrative_market_overview_payload"
    payload = ctx.tool_call_cache.get(cache_key)
    if payload is None:
        payload = build_narrative_market_overview(ctx)
        ctx.tool_call_cache[cache_key] = payload
    return payload


async def handle_screen_stocks(params: dict, ctx: ToolContext) -> dict:
    return build_screen_stocks(ctx, params)


async def handle_screen_behavioral_cycle(params: dict, ctx: ToolContext) -> dict:
    return build_behavioral_cycle_screen(ctx, params.get("max_results", 8))


async def handle_get_sector_summary(params: dict, ctx: ToolContext) -> dict:
    """获取指定板块内股票详情。"""
    return build_sector_summary(ctx, params.get("sector", ""))


async def handle_get_narrative_sector_summary(params: dict, ctx: ToolContext) -> dict:
    sector = str(params.get("sector", "")).strip()
    cache = ctx.tool_call_cache.setdefault("_narrative_sector_summary_cache", {})
    if sector in cache:
        return cache[sector]
    if len(cache) >= 2:
        result = {
            "budget_exhausted": True,
            "limit": 2,
            "instruction": "Use the two sector summaries already returned; do not retry today.",
        }
        if is_current_contract(getattr(ctx, "tool_contract_version", None)):
            result.update(
                {
                    "success": False,
                    "error": "叙事板块工具今日两个板块查询预算已耗尽。",
                    "error_code": "daily_tool_budget_exhausted",
                    "retryable": False,
                    "correction": {"instruction": "使用已经返回的两个板块结果继续判断，不要重试。"},
                }
            )
        return result
    payload = build_narrative_sector_summary(ctx, sector)
    cache[sector] = payload
    ctx.tool_call_cache["_narrative_sector_summary_calls"] = len(cache)
    return payload


GET_MARKET_OVERVIEW = ToolDefinition(
    name="get_market_overview",
    description="查看全市场概览：涨跌家数、板块涨幅前5/跌幅前5",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_get_market_overview,
)

GET_NARRATIVE_MARKET_OVERVIEW = ToolDefinition(
    name="get_narrative_market_overview",
    description="查看全市场的板块1/5/20日强度、上涨扩散、强势主线和早期轮动候选。",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_get_narrative_market_overview,
)

SCREEN_STOCKS = ToolDefinition(
    name="screen_stocks",
    description="按条件筛选股票：价格、涨跌幅、成交量、行业",
    parameters={
        "type": "object",
        "properties": {
            "price_min": {"type": "number", "description": "最低价格"},
            "price_max": {"type": "number", "description": "最高价格"},
            "change_pct_min": {"type": "number", "description": "最小涨跌幅(%)"},
            "change_pct_max": {"type": "number", "description": "最大涨跌幅(%)"},
            "volume_min": {"type": "integer", "description": "最小成交量"},
            "industry": {"type": "string", "description": "行业名称过滤（如：电力设备）"},
            "sort_by": {
                "type": "string",
                "enum": ["change_5d", "change_1d", "volume"],
                "description": "排序方式，默认按5日涨幅",
            },
            "max_results": {"type": "integer", "description": "最多返回数量，默认10，最大30"},
        },
        "required": [],
    },
    handler=handle_screen_stocks,
)

SCREEN_BEHAVIORAL_CYCLE = ToolDefinition(
    name="screen_behavioral_cycle",
    description=(
        "用严格点时的120日量价数据，对全市场计算低位建仓候选、试盘、洗盘和确认拉升阶段；"
        "返回阶段得分、20/60日结构、ATR、量比、CLV、OBV流、支撑阻力、失效价与风险标记。"
        "阶段标签是可证伪的行为假设，不代表已知的主力意图。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "返回候选数，默认8，最多20",
            }
        },
        "required": [],
    },
    handler=handle_screen_behavioral_cycle,
)

GET_SECTOR_SUMMARY = ToolDefinition(
    name="get_sector_summary",
    description="查看指定板块详情：板块内股票涨跌幅排名、平均涨幅",
    parameters={
        "type": "object",
        "properties": {
            "sector": {
                "type": "string",
                "description": "板块名称，如：电力设备、医药生物、金融行业",
            },
        },
        "required": ["sector"],
    },
    handler=handle_get_sector_summary,
)

GET_NARRATIVE_SECTOR_SUMMARY = ToolDefinition(
    name="get_narrative_sector_summary",
    description="查看指定板块的1/5/20日强度、上涨扩散和板块内持续性龙头排名。",
    parameters={
        "type": "object",
        "properties": {
            "sector": {
                "type": "string",
                "description": "板块名称，如：电力设备、医药生物、金融行业",
            },
        },
        "required": ["sector"],
    },
    handler=handle_get_narrative_sector_summary,
)
