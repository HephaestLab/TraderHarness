"""Deterministic, point-in-time tests for the behavioral-cycle screen."""

from __future__ import annotations

import math
import warnings
from decimal import Decimal

import numpy as np
import pandas as pd

from traderharness.core.portfolio import Portfolio
from traderharness.tools.analysis import build_behavioral_cycle_screen
from traderharness.tools.registry import ToolContext


def _frame(*, breakout: bool, future_close: float = 99.0) -> pd.DataFrame:
    dates = list(pd.bdate_range("2024-01-02", periods=71).date)
    close = np.linspace(9.2, 10.0, 70)
    volume = np.full(70, 1000.0)
    if breakout:
        close[-1] = 11.5
        volume[-1] = 3000.0
    frame = pd.DataFrame(
        {
            "date": dates[:70],
            "open": close - 0.1,
            "high": close + 0.1,
            "low": close - 0.2,
            "close": close,
            "volume": volume,
        }
    )
    future = pd.DataFrame(
        {
            "date": [dates[70]],
            "open": [future_close],
            "high": [future_close],
            "low": [future_close],
            "close": [future_close],
            "volume": [9_999_999.0],
        }
    )
    return pd.concat([frame, future], ignore_index=True)


def _ctx() -> ToolContext:
    flat_dates = list(pd.bdate_range("2024-01-02", periods=70).date)
    flat = pd.DataFrame(
        {
            "date": flat_dates,
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 0.0,
        }
    )
    return ToolContext(
        current_date=list(pd.bdate_range("2024-01-02", periods=71).date)[70],
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily={
            "000001": _frame(breakout=True),
            "000002": _frame(breakout=False),
            "000003": flat,
        },
    )


def _assert_finite(value):
    if isinstance(value, dict):
        for item in value.values():
            _assert_finite(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite(item)
    elif isinstance(value, float):
        assert math.isfinite(value)


def test_screen_finds_confirmed_markup_without_runtime_warnings():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = build_behavioral_cycle_screen(_ctx(), max_results=8)

    assert caught == []
    assert result["sample_size"] == 3
    assert result["eligible_size"] == 3
    assert result["candidates"][0]["code"] == "000001"
    assert result["candidates"][0]["stage"] == "markup"
    assert result["candidates"][0]["breakout_20d_pct"] > 0
    _assert_finite(result)


def test_screen_is_point_in_time_and_ignores_future_rows():
    baseline = _ctx()
    changed = _ctx()
    changed.preloaded_daily["000001"] = _frame(breakout=True, future_close=0.01)

    assert build_behavioral_cycle_screen(baseline) == build_behavioral_cycle_screen(changed)


def test_screen_caps_result_count():
    ctx = _ctx()
    ctx.preloaded_daily.update(
        {f"30000{i}": _frame(breakout=True) for i in range(4, 10)}
    )

    result = build_behavioral_cycle_screen(ctx, max_results=3)

    assert len(result["candidates"]) == 3
    assert [row["code"] for row in result["candidates"]] == sorted(
        row["code"] for row in result["candidates"]
    )
