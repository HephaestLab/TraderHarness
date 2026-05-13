"""Tests for MarketProfile — extensible market rules."""

from decimal import Decimal

import pytest

from finharness.core.market_profile import (
    AShareProfile,
    MarketProfile,
)


class TestAShareProfile:
    """A-share market rules: T+1, ±10%/±20% limits, 100-lot, fees."""

    def test_price_limits_normal_stock(self):
        profile = AShareProfile()
        prev_close = Decimal("100.00")
        limit_up, limit_down = profile.price_limits("600519", prev_close)
        assert limit_up == Decimal("110.00")
        assert limit_down == Decimal("90.00")

    def test_price_limits_star_market(self):
        profile = AShareProfile()
        prev_close = Decimal("100.00")
        limit_up, limit_down = profile.price_limits("688001", prev_close)
        assert limit_up == Decimal("120.00")
        assert limit_down == Decimal("80.00")

    def test_price_limits_chinext(self):
        """创业板 300xxx also ±20%."""
        profile = AShareProfile()
        prev_close = Decimal("50.00")
        limit_up, limit_down = profile.price_limits("300001", prev_close)
        assert limit_up == Decimal("60.00")
        assert limit_down == Decimal("40.00")

    def test_round_lot(self):
        profile = AShareProfile()
        assert profile.round_lot(150) == 100
        assert profile.round_lot(99) == 0
        assert profile.round_lot(500) == 500
        assert profile.round_lot(0) == 0

    def test_min_lot_size(self):
        profile = AShareProfile()
        assert profile.min_lot == 100

    def test_settlement_days(self):
        """A-shares: T+1 settlement."""
        profile = AShareProfile()
        assert profile.settlement_days == 1

    def test_commission(self):
        profile = AShareProfile()
        amount = Decimal("10000.00")
        comm = profile.buy_commission(amount)
        assert comm >= Decimal("5.00")  # min 5 yuan

    def test_commission_minimum(self):
        profile = AShareProfile()
        amount = Decimal("100.00")  # small trade
        comm = profile.buy_commission(amount)
        assert comm == Decimal("5.00")

    def test_sell_fees_include_stamp_tax(self):
        profile = AShareProfile()
        amount = Decimal("100000.00")
        comm, stamp = profile.sell_fees(amount)
        assert comm >= Decimal("5.00")
        assert stamp == Decimal("100.00")  # 0.1%

    def test_is_wide_limit_stock(self):
        profile = AShareProfile()
        assert profile.is_wide_limit("688001") is True
        assert profile.is_wide_limit("300123") is True
        assert profile.is_wide_limit("600519") is False
        assert profile.is_wide_limit("000001") is False

    def test_protocol_interface(self):
        """AShareProfile implements MarketProfile protocol."""
        profile = AShareProfile()
        assert isinstance(profile, MarketProfile)
