"""Portfolio + PortfolioView — position management with A-share rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
MIN_COMMISSION = Decimal("5.00")


@dataclass
class Position:
    stock_code: str
    quantity: int
    avg_cost: Decimal
    buy_date: date
    _last_buy_date: date | None = field(default=None, init=False, repr=False)
    _last_buy_qty: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        self._last_buy_date = self.buy_date
        self._last_buy_qty = self.quantity

    def sellable_quantity(self, current_date: date) -> int:
        if self._last_buy_date == current_date:
            return max(0, self.quantity - self._last_buy_qty)
        return self.quantity

    def market_value_at(self, price: Decimal) -> Decimal:
        return (price * self.quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class Portfolio:
    """Simulated trading portfolio with cash, positions, and equity tracking."""

    def __init__(self, initial_cash: Decimal) -> None:
        self.cash: Decimal = initial_cash.quantize(TWO_PLACES)
        self.positions: dict[str, Position] = {}
        self._equity_history: list[tuple[date, Decimal]] = []

    def buy(
        self,
        stock_code: str,
        stock_name: str,
        price: Decimal,
        quantity: int,
        trade_date: date,
        commission_rate: Decimal = Decimal("0.00025"),
    ) -> dict:
        if quantity <= 0:
            raise ValueError("买入数量必须大于 0")
        if quantity % 100 != 0:
            raise ValueError(f"买入数量必须是 100 的整数倍，当前: {quantity}")

        amount = (price * quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        commission = (amount * commission_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if commission < MIN_COMMISSION:
            commission = MIN_COMMISSION
        total_cost = amount + commission

        if total_cost > self.cash:
            raise ValueError(f"资金不足: 需要 {total_cost}，可用 {self.cash}")

        self.cash -= total_cost

        if stock_code in self.positions:
            pos = self.positions[stock_code]
            old_total = pos.avg_cost * pos.quantity
            new_total = old_total + amount
            pos.quantity += quantity
            pos.avg_cost = (new_total / pos.quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if pos._last_buy_date == trade_date:
                pos._last_buy_qty += quantity
            else:
                pos._last_buy_date = trade_date
                pos._last_buy_qty = quantity
        else:
            self.positions[stock_code] = Position(
                stock_code=stock_code,
                quantity=quantity,
                avg_cost=price.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                buy_date=trade_date,
            )

        return {
            "action": "buy",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "commission": commission,
            "total_cost": total_cost,
            "trade_date": trade_date,
        }

    def sell(
        self,
        stock_code: str,
        price: Decimal,
        quantity: int,
        trade_date: date,
        commission_rate: Decimal = Decimal("0.00025"),
        stamp_tax_rate: Decimal = Decimal("0.001"),
    ) -> dict:
        if quantity <= 0:
            raise ValueError("卖出数量必须大于 0")
        if stock_code not in self.positions:
            raise ValueError(f"无持仓: {stock_code}")

        pos = self.positions[stock_code]
        if quantity > pos.quantity:
            raise ValueError(
                f"持仓不足: 持有 {pos.quantity} 股，尝试卖出 {quantity} 股"
            )

        sellable = pos.sellable_quantity(trade_date)
        if quantity > sellable:
            raise ValueError(
                f"T+1 限制: {stock_code} 当天买入部分不可卖出，"
                f"可卖 {sellable} 股，尝试卖出 {quantity} 股"
            )

        amount = (price * quantity).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        commission = (amount * commission_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if commission < MIN_COMMISSION:
            commission = MIN_COMMISSION
        stamp_tax = (amount * stamp_tax_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_fee = commission + stamp_tax
        net_income = amount - total_fee

        self.cash += net_income

        pos.quantity -= quantity
        if pos.quantity == 0:
            del self.positions[stock_code]

        return {
            "action": "sell",
            "stock_code": stock_code,
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "total_fee": total_fee,
            "net_income": net_income,
            "trade_date": trade_date,
        }

    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        market_value = sum(
            (prices.get(code, pos.avg_cost) * pos.quantity)
            for code, pos in self.positions.items()
        )
        return (self.cash + Decimal(market_value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def record_equity(self, trade_date: date, prices: dict[str, Decimal]) -> None:
        self._equity_history.append((trade_date, self.total_value(prices)))

    @property
    def equity_curve(self) -> list[tuple[date, Decimal]]:
        return list(self._equity_history)


class PortfolioView:
    """Read-only proxy — agents see this, cannot mutate."""

    def __init__(self, portfolio: Portfolio) -> None:
        self._portfolio = portfolio

    @property
    def cash(self) -> Decimal:
        return self._portfolio.cash

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._portfolio.positions)

    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        return self._portfolio.total_value(prices)

    @property
    def equity_curve(self) -> list[tuple[date, Decimal]]:
        return self._portfolio.equity_curve
