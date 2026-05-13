"""Tests for Benchmark (BuyAndHold baseline)."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.core.benchmark import BuyAndHoldBenchmark


class TestBuyAndHoldBenchmark:
    def test_creates_with_initial_cash(self):
        bm = BuyAndHoldBenchmark(
            stock_codes=["600519", "000001"],
            initial_cash=Decimal("1000000"),
        )
        assert bm.portfolio.cash == Decimal("1000000.00")

    def test_buy_on_first_day(self):
        bm = BuyAndHoldBenchmark(
            stock_codes=["600519"],
            initial_cash=Decimal("1000000"),
        )
        prices = {"600519": Decimal("1800.00")}
        bm.on_first_day(date(2024, 3, 4), prices)
        assert "600519" in bm.portfolio.positions
        assert bm.portfolio.positions["600519"].quantity > 0

    def test_equal_weight_allocation(self):
        bm = BuyAndHoldBenchmark(
            stock_codes=["600519", "000001"],
            initial_cash=Decimal("1000000"),
        )
        prices = {"600519": Decimal("1800.00"), "000001": Decimal("10.00")}
        bm.on_first_day(date(2024, 3, 4), prices)
        assert "600519" in bm.portfolio.positions
        assert "000001" in bm.portfolio.positions

    def test_holds_positions_on_subsequent_days(self):
        bm = BuyAndHoldBenchmark(
            stock_codes=["600519"],
            initial_cash=Decimal("1000000"),
        )
        prices = {"600519": Decimal("1800.00")}
        bm.on_first_day(date(2024, 3, 4), prices)
        qty_after_buy = bm.portfolio.positions["600519"].quantity
        bm.on_day(date(2024, 3, 5), prices)
        assert bm.portfolio.positions["600519"].quantity == qty_after_buy

    def test_records_equity(self):
        bm = BuyAndHoldBenchmark(
            stock_codes=["600519"],
            initial_cash=Decimal("1000000"),
        )
        prices = {"600519": Decimal("1800.00")}
        bm.on_first_day(date(2024, 3, 4), prices)
        bm.on_day(date(2024, 3, 5), {"600519": Decimal("1850.00")})
        assert len(bm.portfolio.equity_curve) >= 1
