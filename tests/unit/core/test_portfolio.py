"""Tests for Portfolio + PortfolioView."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.core.portfolio import Portfolio, PortfolioView, Position


class TestPosition:
    def test_sellable_quantity_same_day(self):
        pos = Position(
            stock_code="600519", quantity=500,
            avg_cost=Decimal("1800.00"), buy_date=date(2024, 3, 4),
        )
        assert pos.sellable_quantity(date(2024, 3, 4)) == 0

    def test_sellable_quantity_next_day(self):
        pos = Position(
            stock_code="600519", quantity=500,
            avg_cost=Decimal("1800.00"), buy_date=date(2024, 3, 4),
        )
        assert pos.sellable_quantity(date(2024, 3, 5)) == 500

    def test_market_value_at_price(self):
        pos = Position(
            stock_code="600519", quantity=100,
            avg_cost=Decimal("1800.00"), buy_date=date(2024, 3, 4),
        )
        assert pos.market_value_at(Decimal("1900.00")) == Decimal("190000.00")


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        assert p.cash == Decimal("1000000.00")
        assert p.positions == {}

    def test_buy_creates_position(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        trade = p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        assert "600519" in p.positions
        assert p.positions["600519"].quantity == 100
        assert trade["action"] == "buy"

    def test_buy_deducts_cash_with_commission(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        # 1800*100=180000, comm=max(180000*0.00025,5)=45
        expected = Decimal("1000000") - Decimal("180000") - Decimal("45.00")
        assert p.cash == expected

    def test_buy_minimum_commission(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("000001", "平安银行", Decimal("10.00"), 100, date(2024, 3, 4))
        expected = Decimal("1000000") - Decimal("1000") - Decimal("5.00")
        assert p.cash == expected

    def test_buy_adds_to_existing(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        p.buy("600519", "贵州茅台", Decimal("1900.00"), 100, date(2024, 3, 5))
        assert p.positions["600519"].quantity == 200

    def test_buy_invalid_lot(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        with pytest.raises(ValueError, match="100 的整数倍"):
            p.buy("600519", "贵州茅台", Decimal("1800.00"), 50, date(2024, 3, 4))

    def test_buy_insufficient_funds(self):
        p = Portfolio(initial_cash=Decimal("1000"))
        with pytest.raises(ValueError, match="资金不足"):
            p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))

    def test_sell_removes_position(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        p.sell("600519", Decimal("1900.00"), 100, date(2024, 3, 5))
        assert "600519" not in p.positions

    def test_sell_partial(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 200, date(2024, 3, 4))
        p.sell("600519", Decimal("1900.00"), 100, date(2024, 3, 5))
        assert p.positions["600519"].quantity == 100

    def test_sell_t_plus_1(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        with pytest.raises(ValueError, match="T\\+1"):
            p.sell("600519", Decimal("1900.00"), 100, date(2024, 3, 4))

    def test_sell_stamp_tax(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        trade = p.sell("600519", Decimal("1900.00"), 100, date(2024, 3, 5))
        assert trade["stamp_tax"] == Decimal("190.00")

    def test_sell_no_position(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        with pytest.raises(ValueError, match="无持仓"):
            p.sell("600519", Decimal("1900.00"), 100, date(2024, 3, 5))

    def test_total_value(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        prices = {"600519": Decimal("1900.00")}
        total = p.total_value(prices)
        assert total > Decimal("1000000")

    def test_record_equity(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.record_equity(date(2024, 3, 4), {})
        assert len(p.equity_curve) == 1
        assert p.equity_curve[0] == (date(2024, 3, 4), Decimal("1000000.00"))


class TestPortfolioView:
    def test_view_cash(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        view = PortfolioView(p)
        assert view.cash == Decimal("1000000.00")

    def test_view_positions(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        view = PortfolioView(p)
        assert "600519" in view.positions

    def test_view_no_buy(self):
        view = PortfolioView(Portfolio(initial_cash=Decimal("1000000")))
        assert not hasattr(view, "buy")

    def test_view_no_sell(self):
        view = PortfolioView(Portfolio(initial_cash=Decimal("1000000")))
        assert not hasattr(view, "sell")

    def test_view_total_value(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        view = PortfolioView(p)
        prices = {"600519": Decimal("1900.00")}
        assert view.total_value(prices) == p.total_value(prices)

    def test_view_positions_immutable(self):
        p = Portfolio(initial_cash=Decimal("1000000"))
        p.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 3, 4))
        view = PortfolioView(p)
        view.positions.pop("600519", None)
        assert "600519" in p.positions
