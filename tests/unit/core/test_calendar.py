"""Tests for Chinese trading calendar."""

from datetime import date

import pytest

from traderharness.core.calendar import TradingCalendar


class TestTradingCalendar:
    """Chinese A-share trading calendar with holidays."""

    def test_weekdays_are_trading_days(self):
        cal = TradingCalendar()
        # 2024-03-04 is Monday
        assert cal.is_trading_day(date(2024, 3, 4)) is True

    def test_weekends_are_not_trading_days(self):
        cal = TradingCalendar()
        assert cal.is_trading_day(date(2024, 3, 9)) is False  # Saturday
        assert cal.is_trading_day(date(2024, 3, 10)) is False  # Sunday

    def test_spring_festival_2024(self):
        """春节 2024: Feb 9 - Feb 17."""
        cal = TradingCalendar()
        assert cal.is_trading_day(date(2024, 2, 9)) is False
        assert cal.is_trading_day(date(2024, 2, 12)) is False
        assert cal.is_trading_day(date(2024, 2, 15)) is False

    def test_national_day_2024(self):
        """国庆 2024: Oct 1-7."""
        cal = TradingCalendar()
        assert cal.is_trading_day(date(2024, 10, 1)) is False
        assert cal.is_trading_day(date(2024, 10, 4)) is False

    def test_weekend_workday_compensation(self):
        """调休日 — 周末上班 should be trading day."""
        cal = TradingCalendar()
        # 2024-02-04 (Sun) is a compensation workday for Spring Festival
        assert cal.is_trading_day(date(2024, 2, 4)) is True

    def test_get_trading_days_range(self):
        cal = TradingCalendar()
        days = cal.get_trading_days(date(2024, 3, 4), date(2024, 3, 8))
        assert len(days) == 5  # Mon-Fri, no holidays
        assert days[0] == date(2024, 3, 4)
        assert days[-1] == date(2024, 3, 8)

    def test_get_trading_days_skips_weekend(self):
        cal = TradingCalendar()
        days = cal.get_trading_days(date(2024, 3, 8), date(2024, 3, 12))
        # Fri, Mon, Tue (skips Sat/Sun)
        assert len(days) == 3

    def test_next_trading_day(self):
        cal = TradingCalendar()
        # Friday -> next Monday
        assert cal.next_trading_day(date(2024, 3, 8)) == date(2024, 3, 11)

    def test_prev_trading_day(self):
        cal = TradingCalendar()
        # Monday -> prev Friday
        assert cal.prev_trading_day(date(2024, 3, 11)) == date(2024, 3, 8)

    def test_trading_days_count(self):
        cal = TradingCalendar()
        count = cal.trading_days_between(date(2024, 1, 2), date(2024, 12, 31))
        # A-share ~243 trading days in 2024 (depends on holiday data completeness)
        assert 240 <= count <= 252

    def test_empty_range(self):
        cal = TradingCalendar()
        days = cal.get_trading_days(date(2024, 3, 9), date(2024, 3, 10))
        assert days == []  # Weekend only
