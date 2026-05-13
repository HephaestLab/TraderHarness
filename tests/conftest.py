"""Shared test fixtures for FinHarness."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def sample_trading_dates() -> list[date]:
    """A short list of consecutive trading dates (no weekends/holidays)."""
    return [
        date(2024, 3, 4),  # Mon
        date(2024, 3, 5),  # Tue
        date(2024, 3, 6),  # Wed
        date(2024, 3, 7),  # Thu
        date(2024, 3, 8),  # Fri
    ]


@pytest.fixture
def sample_stock_code() -> str:
    return "600519"  # Kweichow Moutai


@pytest.fixture
def initial_cash() -> float:
    return 1_000_000.0
