"""MatchingEngine — order validation and execution with market rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from finharness.core.market_profile import MarketProfile
from finharness.core.portfolio import Portfolio


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    stock_code: str
    side: OrderSide
    price: Decimal
    quantity: int
    trade_date: date
    stock_name: str = ""
    reasoning: str = ""


@dataclass
class OrderResult:
    success: bool
    reason: str = ""
    trade: dict | None = None


class MatchingEngine:
    """Validates and executes orders against market rules."""

    def __init__(self, profile: MarketProfile) -> None:
        self._profile = profile

    def execute(
        self,
        order: Order,
        portfolio: Portfolio,
        prev_close: Decimal,
        is_suspended: bool = False,
    ) -> OrderResult:
        if is_suspended:
            return OrderResult(success=False, reason=f"{order.stock_code} 停牌")

        limit_up, limit_down = self._profile.price_limits(order.stock_code, prev_close)
        if order.price >= limit_up:
            return OrderResult(
                success=False,
                reason=f"{order.stock_code} 涨停 (涨停价 {limit_up})",
            )
        if order.price <= limit_down:
            return OrderResult(
                success=False,
                reason=f"{order.stock_code} 跌停 (跌停价 {limit_down})",
            )

        if order.side == OrderSide.BUY:
            return self._execute_buy(order, portfolio)
        return self._execute_sell(order, portfolio)

    def _execute_buy(self, order: Order, portfolio: Portfolio) -> OrderResult:
        quantity = self._profile.round_lot(order.quantity)
        if quantity <= 0:
            return OrderResult(
                success=False,
                reason=f"买入数量 {order.quantity} 不足1手({self._profile.min_lot}股)",
            )
        try:
            trade = portfolio.buy(
                order.stock_code,
                order.stock_name,
                order.price,
                quantity,
                order.trade_date,
            )
            return OrderResult(success=True, trade=trade)
        except ValueError as e:
            return OrderResult(success=False, reason=str(e))

    def _execute_sell(self, order: Order, portfolio: Portfolio) -> OrderResult:
        try:
            trade = portfolio.sell(
                order.stock_code,
                order.price,
                order.quantity,
                order.trade_date,
            )
            return OrderResult(success=True, trade=trade)
        except ValueError as e:
            return OrderResult(success=False, reason=str(e))
