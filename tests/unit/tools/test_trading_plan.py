"""Structured position-plan enforcement for behavior agents."""

from datetime import date
from decimal import Decimal

import pytest

from traderharness.core.portfolio import Portfolio
from traderharness.tools.portfolio import handle_get_position
from traderharness.tools.registry import ToolContext
from traderharness.tools.trading import handle_place_order


class _Bus:
    def __init__(self, portfolio: Portfolio, price: str = "10.00") -> None:
        self.portfolio = portfolio
        self.price = Decimal(price)
        self.calls = 0
        self.conditional_orders = []
        self.current_date = date(2024, 3, 1)

    def get_execution_price(self, code: str, window: str = "open") -> Decimal:
        return self.price

    def place_order(
        self,
        *,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str,
        reasoning: str,
        window: str,
    ) -> dict:
        self.calls += 1
        if side == "buy":
            trade = self.portfolio.buy(
                stock_code, stock_name, self.price, quantity, self.current_date
            )
        else:
            pos = self.portfolio.positions[stock_code]
            sellable = pos.sellable_quantity(self.current_date)
            sold = sellable if quantity == 0 else min(quantity, sellable)
            avg_cost = pos.avg_cost
            trade = self.portfolio.sell(stock_code, self.price, sold, self.current_date)
            trade["pnl"] = float(trade["net_income"]) - float(avg_cost * sold)
        return {"success": True, "trade": trade}

    def create_conditional_order(self, **kwargs) -> dict:
        order = {"order_id": f"cond-{len(self.conditional_orders) + 1:04d}", **kwargs}
        self.conditional_orders.append(order)
        return order


def _ctx(*, price: str = "10.00", day_index: int = 10) -> tuple[ToolContext, _Bus]:
    portfolio = Portfolio(Decimal("1000000"))
    bus = _Bus(portfolio, price)
    ctx = ToolContext(
        current_date=date(2024, 3, 1),
        current_phase="open_window",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        execution_price={"600519": Decimal(price)},
        close_prices={"600519": Decimal(price)},
        agent_id="behavioral-cycle",
        require_structured_plan=True,
        minimum_holding_days=5,
        day_index=day_index,
        max_position_pct=100.0,
        _bus=bus,
    )
    ctx.tool_call_cache["_position_plans"] = {}
    return ctx, bus


def _buy_args() -> dict:
    return {
        "action": "buy",
        "stock_code": "600519",
        "stock_name": "company",
        "quantity": 30_000,
        "reasoning": "confirmed crowd pressure",
        "behavior_hypothesis": "attention shock followed by confirmed demand",
        "confirmation_level": 9.80,
        "original_structural_stop": 9.40,
        "exit_condition": "price reaches the original structural stop",
        "expected_holding_days": 15,
    }


@pytest.mark.asyncio
async def test_structured_agent_rejects_buy_without_frozen_plan():
    ctx, bus = _ctx()

    result = await handle_place_order(
        {
            "action": "buy",
            "stock_code": "600519",
            "quantity": 30_000,
            "reasoning": "missing plan",
        },
        ctx,
    )

    assert result["success"] is False
    assert "结构化" in result["error"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_buy_freezes_plan_and_position_reports_trading_days():
    ctx, bus = _ctx()
    result = await handle_place_order(_buy_args(), ctx)
    assert result["success"] is True

    plan = ctx.tool_call_cache["_position_plans"]["600519"]
    assert plan["original_structural_stop"] == 9.4
    assert plan["entry_day_index"] == 10
    assert plan["minimum_holding_days"] == 5
    assert plan["conditional_order_id"] == "cond-0001"
    assert bus.conditional_orders[0]["comparator"] == "price_lte"
    assert bus.conditional_orders[0]["trigger_price"] == Decimal("9.4")
    assert bus.conditional_orders[0]["not_before_day_index"] == 11

    ctx.day_index = 12
    ctx.current_date = date(2024, 3, 5)
    position = await handle_get_position({"stock_code": "600519"}, ctx)
    assert position["holding_trading_days"] == 2
    assert position["position_plan"]["original_structural_stop"] == 9.4


@pytest.mark.asyncio
async def test_early_sell_above_original_stop_is_rejected():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 4)
    bus.price = Decimal("9.60")
    ctx.current_date = bus.current_date
    ctx.day_index = 11
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    result = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "long upper shadow therefore distribution",
        },
        ctx,
    )

    assert result["success"] is False
    assert "最短持有" in result["error"]
    assert result["position_plan"]["original_structural_stop"] == 9.4
    assert ctx.portfolio.positions["600519"].quantity == 30_000
    assert bus.calls == 1


@pytest.mark.asyncio
async def test_early_hard_stop_requires_full_exit_and_removes_plan():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 4)
    bus.price = Decimal("9.35")
    ctx.current_date = bus.current_date
    ctx.day_index = 11
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    partial = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 10_000,
            "reasoning": "hard stop",
        },
        ctx,
    )
    assert partial["success"] is False
    assert "全部" in partial["error"]

    full = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "hard stop",
        },
        ctx,
    )
    assert full["success"] is True
    assert "600519" not in ctx.portfolio.positions
    assert "600519" not in ctx.tool_call_cache["_position_plans"]


@pytest.mark.asyncio
async def test_sell_after_minimum_holding_period_is_allowed_above_stop():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 8)
    bus.price = Decimal("10.50")
    ctx.current_date = bus.current_date
    ctx.day_index = 15
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    result = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "planned exit after minimum hold",
        },
        ctx,
    )

    assert result["success"] is True
