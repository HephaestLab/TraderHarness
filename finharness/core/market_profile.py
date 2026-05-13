"""MarketProfile — extensible market rules (price limits, lots, fees)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol, runtime_checkable

TWO_PLACES = Decimal("0.01")
MIN_COMMISSION = Decimal("5.00")


@runtime_checkable
class MarketProfile(Protocol):
    """Protocol for market-specific trading rules."""

    @property
    def settlement_days(self) -> int: ...

    @property
    def min_lot(self) -> int: ...

    def price_limits(self, stock_code: str, prev_close: Decimal) -> tuple[Decimal, Decimal]: ...

    def round_lot(self, quantity: int) -> int: ...

    def buy_commission(self, amount: Decimal) -> Decimal: ...

    def sell_fees(self, amount: Decimal) -> tuple[Decimal, Decimal]: ...

    def is_wide_limit(self, stock_code: str) -> bool: ...


class AShareProfile:
    """A-share (China mainland) market rules.

    - Normal stocks: ±10% daily price limit
    - STAR Market (688xxx) / ChiNext (300xxx): ±20%
    - Round lot: 100 shares
    - Settlement: T+1
    - Commission: 0.025%, min 5 yuan
    - Stamp tax (sell only): 0.1%
    """

    _COMMISSION_RATE = Decimal("0.00025")
    _STAMP_TAX_RATE = Decimal("0.001")

    @property
    def settlement_days(self) -> int:
        return 1

    @property
    def min_lot(self) -> int:
        return 100

    def price_limits(self, stock_code: str, prev_close: Decimal) -> tuple[Decimal, Decimal]:
        pct = Decimal("0.20") if self.is_wide_limit(stock_code) else Decimal("0.10")
        limit_up = (prev_close * (1 + pct)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        limit_down = (prev_close * (1 - pct)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return limit_up, limit_down

    def round_lot(self, quantity: int) -> int:
        return (quantity // self.min_lot) * self.min_lot

    def buy_commission(self, amount: Decimal) -> Decimal:
        comm = (amount * self._COMMISSION_RATE).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return max(comm, MIN_COMMISSION)

    def sell_fees(self, amount: Decimal) -> tuple[Decimal, Decimal]:
        comm = self.buy_commission(amount)
        stamp = (amount * self._STAMP_TAX_RATE).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return comm, stamp

    def is_wide_limit(self, stock_code: str) -> bool:
        return stock_code.startswith("688") or stock_code.startswith("300")
