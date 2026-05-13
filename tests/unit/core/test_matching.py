"""Tests for Order Matching Engine."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.core.matching import MatchingEngine, Order, OrderResult, OrderSide
from finharness.core.market_profile import AShareProfile
from finharness.core.portfolio import Portfolio


class TestMatchingEngine:
    def setup_method(self):
        self.engine = MatchingEngine(AShareProfile())
        self.portfolio = Portfolio(initial_cash=Decimal("1000000"))

    def test_buy_order_success(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=100,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1750.00"))
        assert result.success is True
        assert "600519" in self.portfolio.positions

    def test_sell_order_success(self):
        self.portfolio.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        order = Order(
            stock_code="600519", side=OrderSide.SELL,
            price=Decimal("1900.00"), quantity=100,
            trade_date=date(2024, 3, 5),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1800.00"))
        assert result.success is True
        assert "600519" not in self.portfolio.positions

    def test_buy_rejected_limit_up(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1925.00"), quantity=100,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1750.00"))
        assert result.success is False
        assert "涨停" in result.reason

    def test_sell_rejected_limit_down(self):
        self.portfolio.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        order = Order(
            stock_code="600519", side=OrderSide.SELL,
            price=Decimal("1575.00"), quantity=100,
            trade_date=date(2024, 3, 5),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1800.00"))
        assert result.success is False
        assert "跌停" in result.reason

    def test_buy_rejected_insufficient_funds(self):
        p = Portfolio(initial_cash=Decimal("1000"))
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=100,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, p, prev_close=Decimal("1750.00"))
        assert result.success is False
        assert "资金不足" in result.reason

    def test_sell_rejected_t_plus_1(self):
        self.portfolio.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        order = Order(
            stock_code="600519", side=OrderSide.SELL,
            price=Decimal("1850.00"), quantity=100,
            trade_date=date(2024, 3, 4),  # same day
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1800.00"))
        assert result.success is False
        assert "T+1" in result.reason

    def test_buy_round_lot_enforced(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=150,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1750.00"))
        assert result.success is True
        assert self.portfolio.positions["600519"].quantity == 100

    def test_buy_less_than_one_lot_rejected(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=50,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1750.00"))
        assert result.success is False

    def test_suspended_stock_rejected(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=100,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(
            order, self.portfolio, prev_close=Decimal("1750.00"), is_suspended=True
        )
        assert result.success is False
        assert "停牌" in result.reason

    def test_result_contains_trade_details(self):
        order = Order(
            stock_code="600519", side=OrderSide.BUY,
            price=Decimal("1800.00"), quantity=100,
            trade_date=date(2024, 3, 4),
        )
        result = self.engine.execute(order, self.portfolio, prev_close=Decimal("1750.00"))
        assert result.trade is not None
        assert result.trade["stock_code"] == "600519"
        assert result.trade["quantity"] == 100
