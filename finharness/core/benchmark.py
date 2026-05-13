"""BuyAndHoldBenchmark — equal-weight buy-and-hold baseline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finharness.core.portfolio import Portfolio


class BuyAndHoldBenchmark:
    """Buys equal weight on first day, holds until the end."""

    def __init__(self, stock_codes: list[str], initial_cash: Decimal) -> None:
        self.stock_codes = stock_codes
        self.portfolio = Portfolio(initial_cash)
        self._bought = False

    def on_first_day(self, trade_date: date, prices: dict[str, Decimal]) -> None:
        if self._bought:
            return
        n = len(self.stock_codes)
        if n == 0:
            return
        allocation = self.portfolio.cash / n
        for code in self.stock_codes:
            price = prices.get(code)
            if price is None or price <= 0:
                continue
            max_qty = int(allocation / price)
            qty = (max_qty // 100) * 100
            if qty <= 0:
                continue
            self.portfolio.buy(code, code, price, qty, trade_date)
        self._bought = True
        self.portfolio.record_equity(trade_date, prices)

    def on_day(self, trade_date: date, prices: dict[str, Decimal]) -> None:
        self.portfolio.record_equity(trade_date, prices)
