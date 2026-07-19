"""TradingBus.get_execution_price — fair matching: no daily-bar fallback.

Fills must come from the visible 5-minute sub-window bar. If 5-minute data is
missing, the environment must refuse to synthesize a price from the daily
open/close bar (that would let an agent see the full day and pick a
favorable price after the fact).
"""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from traderharness.core.engine import MarketData, TradingBus
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile
from traderharness.core.portfolio import Portfolio

CODE = "600519"
TODAY = date(2024, 3, 5)


def _make_bus(daily_df: pd.DataFrame | None = None, min5_df: pd.DataFrame | None = None) -> TradingBus:
    market = MarketData()
    if daily_df is not None:
        market._data[CODE] = daily_df
    if min5_df is not None:
        market.load_5min(CODE, min5_df)
    portfolio = Portfolio(Decimal("1000000"))
    bus = TradingBus(
        market_data=market,
        profile=AShareProfile(),
        portfolio=portfolio,
        event_bus=EventBus(),
    )
    bus._set_date(TODAY)
    return bus


def _daily_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date(2024, 3, 4), TODAY],
            "open": [9.0, 9.5],
            "high": [9.6, 9.8],
            "low": [8.9, 9.3],
            "close": [9.4, 9.6],
            "volume": [1000, 1200],
        }
    )


def _min5_df(bars: list[tuple[int, int, float]]) -> pd.DataFrame:
    """bars: list of (hour, minute, close)."""
    return pd.DataFrame(
        {
            "datetime": [datetime(TODAY.year, TODAY.month, TODAY.day, h, m) for h, m, _ in bars],
            "date": [TODAY] * len(bars),
            "open": [c - 0.05 for _, _, c in bars],
            "high": [c + 0.05 for _, _, c in bars],
            "low": [c - 0.1 for _, _, c in bars],
            "close": [c for _, _, c in bars],
            "volume": [100] * len(bars),
        }
    )


class TestGetExecutionPriceWith5MinData:
    def test_uses_last_bar_close_in_open_1_sub_window(self):
        min5 = _min5_df([(9, 35, 10.1), (9, 40, 10.2), (9, 45, 10.3), (9, 50, 10.35)])
        bus = _make_bus(min5_df=min5)

        price = bus.get_execution_price(CODE, "open_1")

        assert price == Decimal("10.35")

    def test_uses_last_bar_close_in_close_2_sub_window(self):
        min5 = _min5_df([(14, 55, 20.0), (15, 0, 20.5)])
        bus = _make_bus(min5_df=min5)

        price = bus.get_execution_price(CODE, "close_2")

        assert price == Decimal("20.5")

    def test_ignores_bars_outside_requested_sub_window(self):
        # Only an open_2 bar exists; open_1 must not match it.
        min5 = _min5_df([(9, 55, 11.0)])
        bus = _make_bus(min5_df=min5)

        assert bus.get_execution_price(CODE, "open_1") is None
        assert bus.get_execution_price(CODE, "open_2") == Decimal("11.0")


class TestGetExecutionPriceWithout5MinData:
    def test_returns_none_when_5min_data_entirely_missing(self):
        bus = _make_bus(daily_df=_daily_df())

        price = bus.get_execution_price(CODE, "open")

        assert price is None

    def test_does_not_fall_back_to_daily_open_or_close(self):
        daily = _daily_df()
        bus = _make_bus(daily_df=daily)

        price = bus.get_execution_price(CODE, "close")

        # Must NOT equal today's daily close (9.6) or open (9.5) — no fallback.
        assert price is None

    def test_returns_none_when_5min_data_only_covers_other_dates(self):
        min5 = _min5_df([(9, 40, 10.0)])
        min5["date"] = [date(2024, 3, 4)]  # yesterday's bar, not today
        bus = _make_bus(min5_df=min5)

        assert bus.get_execution_price(CODE, "open") is None

    def test_returns_none_for_unknown_stock_code(self):
        bus = _make_bus()

        assert bus.get_execution_price("999999", "open") is None


class TestPlaceOrderErrorMessage:
    def test_place_order_reports_missing_5min_price_as_correctable_error(self):
        bus = _make_bus(daily_df=_daily_df())

        result = bus.place_order(
            agent_id="agent-1",
            stock_code=CODE,
            side="buy",
            quantity=100,
            window="open",
        )

        assert result["success"] is False
        assert "5分钟" in result["error"]
        assert CODE in result["error"]

    def test_place_order_succeeds_when_5min_price_available(self):
        min5 = _min5_df([(9, 35, 10.0), (9, 40, 10.1)])
        bus = _make_bus(min5_df=min5)

        result = bus.place_order(
            agent_id="agent-1",
            stock_code=CODE,
            side="buy",
            quantity=100,
            window="open_1",
        )

        assert result["success"] is True
        assert Decimal(str(result["trade"]["price"])) == Decimal("10.1")
