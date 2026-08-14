"""Sector summary ranking must be fingerprint-stable on equal change_pct ties."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.portfolio import Portfolio
from traderharness.tools.analysis import (
    handle_get_narrative_sector_summary,
    handle_get_sector_summary,
)
from traderharness.tools.registry import ToolContext


@pytest.mark.asyncio
async def test_sector_top_gainers_break_ties_by_code(monkeypatch):
    day = date(2024, 3, 5)
    # Two names with identical +10% moves; code order must decide ranking.
    daily = {
        "300002": pd.DataFrame(
            {
                "date": [date(2024, 3, 3), date(2024, 3, 4)],
                "close": [10.0, 11.0],
            }
        ),
        "300001": pd.DataFrame(
            {
                "date": [date(2024, 3, 3), date(2024, 3, 4)],
                "close": [10.0, 11.0],
            }
        ),
    }
    monkeypatch.setattr(
        "traderharness.tools.analysis.get_stock_industry",
        lambda code: "电子信息",
    )
    ctx = ToolContext(
        agent_id="t",
        current_date=day,
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily=daily,
    )
    result = await handle_get_sector_summary({"sector": "电子信息"}, ctx)
    assert [row["code"] for row in result["top_gainers"]] == ["300001", "300002"]


@pytest.mark.asyncio
async def test_sector_summary_exposes_multi_horizon_breadth_and_leaders(monkeypatch):
    dates = pd.date_range("2024-01-01", periods=25, freq="D").date

    def frame(closes, volumes):
        return pd.DataFrame(
            {
                "date": dates,
                "open": closes,
                "high": [value * 1.01 for value in closes],
                "low": [value * 0.99 for value in closes],
                "close": closes,
                "volume": volumes,
                "amount": [close * volume for close, volume in zip(closes, volumes, strict=True)],
            }
        )

    daily = {
        "300001": frame([10 + index * 0.2 for index in range(25)], [100] * 20 + [180] * 5),
        "300002": frame([10 + index * 0.1 for index in range(25)], [100] * 25),
        "300003": frame([12 - index * 0.03 for index in range(25)], [100] * 25),
    }
    monkeypatch.setattr(
        "traderharness.tools.analysis.get_stock_industry",
        lambda code: "电子信息",
    )
    ctx = ToolContext(
        agent_id="t",
        current_date=date(2024, 2, 1),
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily=daily,
    )

    result = await handle_get_narrative_sector_summary({"sector": "电子信息"}, ctx)

    assert {
        "change_1d_pct",
        "change_5d_pct",
        "change_20d_pct",
        "up_ratio_1d_pct",
        "up_ratio_5d_pct",
        "up_ratio_20d_pct",
        "leaders",
    } <= result.keys()
    assert result["leaders"][0]["code"] == "300001"
    assert result["leaders"][0]["volume_5_to_20"] > 1
    assert result["leaders"][0]["amount_5d_avg_million"] is not None
    assert result["up_ratio_20d_pct"] == pytest.approx(66.67, abs=0.01)

    cached = await handle_get_narrative_sector_summary({"sector": "电子信息"}, ctx)
    assert cached == result
    await handle_get_narrative_sector_summary({"sector": "电子"}, ctx)
    exhausted = await handle_get_narrative_sector_summary({"sector": "信息"}, ctx)
    assert exhausted == {
        "budget_exhausted": True,
        "limit": 2,
        "instruction": "Use the two sector summaries already returned; do not retry today.",
    }
