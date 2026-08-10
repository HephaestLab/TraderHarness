"""Environment-owned conditional orders use the protected TradingBus path."""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from traderharness.core.engine import MarketData, TradingBus
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile
from traderharness.core.portfolio import Portfolio

CODE = "600519"
DAY_1 = date(2024, 3, 4)
DAY_2 = date(2024, 3, 5)


def _bars(day: date, values: list[tuple[int, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": [datetime(day.year, day.month, day.day, h, m) for h, m, _ in values],
            "date": [day] * len(values),
            "open": [price for _, _, price in values],
            "high": [price for _, _, price in values],
            "low": [price for _, _, price in values],
            "close": [price for _, _, price in values],
            "volume": [1000] * len(values),
        }
    )


def _bus() -> TradingBus:
    market = MarketData()
    market._data[CODE] = pd.DataFrame(
        {
            "date": [date(2024, 3, 1), DAY_1, DAY_2],
            "open": [10.0, 10.0, 10.0],
            "high": [10.2, 10.2, 10.1],
            "low": [9.8, 9.5, 9.0],
            "close": [10.0, 9.8, 9.2],
            "volume": [1000, 1000, 1000],
        }
    )
    market.load_5min(
        CODE,
        pd.concat(
            [
                _bars(DAY_1, [(9, 35, 10.0), (9, 50, 9.9)]),
                _bars(DAY_2, [(9, 35, 9.8), (9, 40, 9.35), (9, 45, 9.2)]),
            ],
            ignore_index=True,
        ),
    )
    bus = TradingBus(market, AShareProfile(), Portfolio(Decimal("1000000")), EventBus())
    bus._set_date(DAY_1)
    bus._day_index = 0
    return bus


def test_condition_fills_at_first_qualifying_bar_close_through_place_order():
    bus = _bus()
    buy = bus.place_order("agent", CODE, "buy", 100, window="open_1")
    assert buy["success"]
    order = bus.create_conditional_order(
        agent_id="agent",
        stock_code=CODE,
        side="sell",
        quantity=0,
        comparator="price_lte",
        trigger_price=Decimal("9.40"),
        reasoning="original structural stop",
        created_phase="open_1",
    )

    bus._set_date(DAY_2)
    bus._day_index = 1
    events = bus.process_conditional_orders("agent", "open_1")

    assert len(events) == 1
    assert events[0]["success"] is True
    assert Decimal(str(events[0]["trade"]["price"])) == Decimal("9.35")
    assert events[0]["trade"]["conditional_order_id"] == order["order_id"]
    assert CODE not in bus.portfolio.positions
    assert bus.list_conditional_orders(status="triggered")[0]["status"] == "triggered"


def test_new_condition_never_scans_already_revealed_bars_retroactively():
    bus = _bus()
    bus.create_conditional_order(
        agent_id="agent",
        stock_code=CODE,
        side="buy",
        quantity=100,
        comparator="price_lte",
        trigger_price=Decimal("10.10"),
        reasoning="late limit entry",
        created_phase="open_1",
    )

    assert bus.process_conditional_orders("agent", "open_1") == []


def test_protective_stop_can_only_be_raised_and_updates_are_audited():
    bus = _bus()
    assert bus.place_order("agent", CODE, "buy", 100, window="open_1")["success"]
    order = bus.create_conditional_order(
        agent_id="agent",
        stock_code=CODE,
        side="sell",
        quantity=0,
        comparator="price_lte",
        trigger_price=Decimal("9.40"),
        reasoning="protective stop",
        created_phase="pre_market",
        protective=True,
    )

    rejected = bus.update_conditional_order(
        order["order_id"], trigger_price=Decimal("9.20"), reasoning="loosen risk"
    )
    updated = bus.update_conditional_order(
        order["order_id"], trigger_price=Decimal("9.80"), reasoning="raise on higher low"
    )

    assert rejected["success"] is False
    assert updated["success"] is True
    assert updated["order"]["trigger_price"] == 9.8
    assert len(updated["order"]["revisions"]) == 1

    partial = bus.update_conditional_order(
        order["order_id"], quantity=100, reasoning="partial protective exit"
    )
    assert partial["success"] is False
    assert "全部" in partial["error"]


def test_cancelled_condition_does_not_execute():
    bus = _bus()
    order = bus.create_conditional_order(
        agent_id="agent",
        stock_code=CODE,
        side="buy",
        quantity=100,
        comparator="price_lte",
        trigger_price=Decimal("10.10"),
        reasoning="entry",
        created_phase="pre_market",
    )
    assert bus.cancel_conditional_order(order["order_id"], reasoning="hypothesis invalid")[
        "success"
    ]

    assert bus.process_conditional_orders("agent", "open_1") == []
    assert bus.trade_history == []
