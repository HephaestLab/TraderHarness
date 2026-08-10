"""Conditional-order tools expose audited state without bypassing masking."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.engine import MarketData, TradingBus
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile
from traderharness.core.portfolio import Portfolio
from traderharness.tools.conditional_orders import (
    LIST_CONDITIONAL_ORDERS,
    MANAGE_CONDITIONAL_ORDER,
)
from traderharness.tools.registry import ToolContext, ToolRegistry


def _context() -> ToolContext:
    market = MarketData()
    market._data["600519"] = pd.DataFrame(
        {"date": [date(2024, 3, 4)], "open": [10], "high": [10], "low": [10], "close": [10], "volume": [1]}
    )
    portfolio = Portfolio(Decimal("1000000"))
    portfolio.buy("600519", "贵州茅台", Decimal("10"), 100, date(2024, 3, 4))
    bus = TradingBus(market, AShareProfile(), portfolio, EventBus())
    bus._set_date(date(2024, 3, 5))
    ctx = ToolContext(
        current_date=date(2024, 3, 5),
        current_phase="pre_market",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        agent_id="agent",
        day_index=1,
        _bus=bus,
    )
    ctx.entity_masker = EntityMasker(
        ["600519", "600000"],
        names={"600519": "贵州茅台", "600000": "浦发银行"},
        seed=1,
    )
    return ctx


@pytest.mark.asyncio
async def test_create_list_and_raise_protective_stop_with_masking():
    ctx = _context()
    registry = ToolRegistry()
    registry.register(MANAGE_CONDITIONAL_ORDER)
    registry.register(LIST_CONDITIONAL_ORDERS)
    code = ctx.entity_masker.mask_code("600519")

    created = await registry.execute(
        "manage_conditional_order",
        {
            "operation": "create",
            "action": "sell",
            "stock_code": code,
            "quantity": 0,
            "comparator": "price_lte",
            "trigger_price": 9.4,
            "protective": True,
            "reasoning": "structural stop",
        },
        ctx,
    )
    updated = await registry.execute(
        "manage_conditional_order",
        {
            "operation": "update",
            "order_id": created["order"]["order_id"],
            "trigger_price": 9.8,
            "reasoning": "confirmed higher low",
        },
        ctx,
    )
    listed = await registry.execute("list_conditional_orders", {"status": "active"}, ctx)

    assert created["success"] is True
    assert updated["success"] is True
    assert listed["orders"][0]["stock_code"] == code
    assert listed["orders"][0]["trigger_price"] == 9.8
