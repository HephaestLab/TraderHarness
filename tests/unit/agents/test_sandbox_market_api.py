"""Sandbox MarketAPI surface for quant research (overview/sector/screen/change_pct)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from traderharness.agents.sandbox.api import MarketAPI
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.portfolio import Portfolio
from traderharness.tools.registry import ToolContext

CURRENT = date(2024, 3, 8)
A = "600519"
B = "600000"


def _bars(closes):
    # Bars end the day before CURRENT so date < CURRENT retains the full series.
    return pd.DataFrame(
        {
            "date": [date(2024, 3, d) for d in range(1, 1 + len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [10000] * len(closes),
        }
    )


def _ctx():
    return ToolContext(
        current_date=CURRENT,
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily={
            A: _bars([100, 102, 104, 106, 108, 110]),
            B: _bars([10, 10, 10, 11, 12, 13]),
        },
        agent_id="sandbox_api",
        workspace_root="sandbox_api",
    )


def _industries(code):
    return {A: "白酒", B: "银行"}.get(code, "其他")


def test_get_all_daily_includes_change_pct():
    api = MarketAPI(_ctx())
    df = api.get_all_daily(days=5)
    assert "change_pct" in df.columns
    assert "stock_code" in df.columns
    a_latest = df[df["stock_code"] == A].sort_values("date").iloc[-1]
    assert a_latest["change_pct"] == pytest.approx((110 - 108) / 108 * 100, abs=0.01)


def test_get_all_daily_rejects_offset_kwargs():
    api = MarketAPI(_ctx())
    with pytest.raises(TypeError, match="days"):
        api.get_all_daily(offset=0)
    with pytest.raises(TypeError, match="days"):
        api.get_all_daily(date_offset=-1)


def test_get_all_stocks_aliases_get_stock_list():
    api = MarketAPI(_ctx())
    assert api.get_all_stocks() == api.get_stock_list()
    assert set(api.get_stock_list()) == {A, B}


@patch("traderharness.tools.analysis.get_stock_industry", side_effect=_industries)
def test_get_market_overview(_mock):
    api = MarketAPI(_ctx())
    overview = api.get_market_overview()
    assert overview["up_count"] + overview["down_count"] >= 1
    assert "top_sectors" in overview


@patch("traderharness.tools.analysis.get_stock_industry", side_effect=_industries)
def test_get_sector_summary_and_stocks(_mock):
    api = MarketAPI(_ctx())
    summary = api.get_sector_summary("白酒")
    assert summary["sector"] == "白酒"
    assert summary["stock_count"] >= 1
    stocks = api.get_sector_stocks("白酒")
    assert not stocks.empty
    assert {"stock_code", "close", "change_pct"}.issubset(stocks.columns)


@patch("traderharness.tools.analysis.get_stock_industry", side_effect=_industries)
def test_screen_stocks(_mock):
    api = MarketAPI(_ctx())
    result = api.screen_stocks(max_results=5, sort_by="change_1d")
    assert "stocks" in result
    assert result["total_matched"] >= 1


def test_get_stock_price():
    api = MarketAPI(_ctx())
    quote = api.get_stock_price(A)
    assert quote["stock_code"] == A
    assert quote["close"] == 110.0
    assert "change_pct" in quote


def _bars_with_volumes(closes, volumes):
    return pd.DataFrame(
        {
            "date": [date(2024, 3, d) for d in range(1, 1 + len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": volumes,
        }
    )


def test_get_stock_price_tolerates_nan_volume():
    ctx = _ctx()
    ctx.preloaded_daily[A] = _bars_with_volumes(
        [100, 102, 104, 106, 108, 110],
        [10000, 10000, 10000, 10000, 10000, float("nan")],
    )
    quote = MarketAPI(ctx).get_stock_price(A)
    assert quote["volume"] == 0


@patch("traderharness.tools.analysis.get_stock_industry", side_effect=_industries)
def test_screen_stocks_tolerates_nan_volume(_mock):
    ctx = _ctx()
    ctx.preloaded_daily[A] = _bars_with_volumes(
        [100, 102, 104, 106, 108, 110],
        [10000, 10000, 10000, 10000, 10000, float("nan")],
    )
    result = MarketAPI(ctx).screen_stocks(max_results=5, sort_by="change_1d")
    a_rows = [s for s in result["stocks"] if s["code"] == A]
    assert a_rows and a_rows[0]["volume"] == 0


def test_entity_mask_on_sector_summary():
    ctx = _ctx()
    ctx.entity_masker = EntityMasker(
        [A, B],
        names={A: "贵州茅台", B: "浦发银行"},
        seed=1,
    )
    with patch("traderharness.tools.analysis.get_stock_industry", side_effect=_industries):
        summary = MarketAPI(ctx).get_sector_summary("白酒")
    pseudo = ctx.entity_masker.mask_code(A)
    assert summary["top_gainers"][0]["code"] == pseudo
    assert A not in str(summary)
