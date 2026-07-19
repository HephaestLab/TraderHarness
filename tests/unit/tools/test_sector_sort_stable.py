"""Sector summary ranking must be fingerprint-stable on equal change_pct ties."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.portfolio import Portfolio
from traderharness.tools.analysis import handle_get_sector_summary
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
