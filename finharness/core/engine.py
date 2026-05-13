"""BacktestEngine — drives day-by-day simulation with multi-agent scheduling."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from finharness.core.calendar import TradingCalendar
from finharness.core.events import EventBus
from finharness.core.market_profile import MarketProfile
from finharness.core.matching import MatchingEngine, Order, OrderSide
from finharness.core.portfolio import Portfolio, PortfolioView

logger = logging.getLogger(__name__)


class MarketDataProvider(Protocol):
    """Protocol for fetching price data."""

    def get_price(self, stock_code: str, trade_date: date) -> Decimal | None: ...
    def get_prev_close(self, stock_code: str, trade_date: date) -> Decimal | None: ...


@dataclass
class EngineConfig:
    initial_cash: Decimal = Decimal("1000000")
    profile: MarketProfile | None = None
    calendar: TradingCalendar | None = None


@dataclass
class EngineResult:
    trading_days: int = 0
    start_date: date | None = None
    end_date: date | None = None
    agent_data: dict[str, dict[str, Any]] = field(default_factory=dict)


class _AgentEnvProxy:
    """Per-agent environment proxy exposed during on_day()."""

    def __init__(
        self,
        agent_id: str,
        portfolio_view: PortfolioView,
        engine: "BacktestEngine",
        current_date: date,
    ) -> None:
        self.agent_id = agent_id
        self.portfolio = portfolio_view
        self._engine = engine
        self.current_date = current_date

    async def place_order(
        self,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str = "",
        reasoning: str = "",
    ) -> dict:
        return self._engine._place_order(
            agent_id=agent_id,
            stock_code=stock_code,
            side=side,
            quantity=quantity,
            stock_name=stock_name,
            trade_date=self.current_date,
            reasoning=reasoning,
        )


class BacktestEngine:
    """Core engine: progresses through trading days, dispatches agents."""

    def __init__(
        self,
        config: EngineConfig,
        market_data: MarketDataProvider,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._market_data = market_data
        self._event_bus = event_bus or EventBus()
        self._profile = config.profile
        self._calendar = config.calendar or TradingCalendar()
        self._matching = MatchingEngine(self._profile) if self._profile else None
        self._portfolios: dict[str, Portfolio] = {}
        self._trade_histories: dict[str, list[dict]] = {}

    async def run(
        self,
        agents: list[Any],
        start_date: date,
        end_date: date,
        breakpoints: list[date] | None = None,
    ) -> EngineResult:
        breakpoints_set = set(breakpoints) if breakpoints else set()
        trading_days = self._calendar.get_trading_days(start_date, end_date)

        for agent in agents:
            self._portfolios[agent.agent_id] = Portfolio(self._config.initial_cash)
            self._trade_histories[agent.agent_id] = []

        self._event_bus.emit("run_start", start_date=start_date, end_date=end_date)

        for current_date in trading_days:
            self._event_bus.emit("day_start", date=current_date)

            for agent in agents:
                portfolio = self._portfolios[agent.agent_id]
                view = PortfolioView(portfolio)
                proxy = _AgentEnvProxy(agent.agent_id, view, self, current_date)
                try:
                    await agent.on_day(proxy, current_date)
                except Exception:
                    logger.exception(
                        "Agent %s error on %s", agent.agent_id, current_date
                    )

                prices = self._get_prices_for_portfolio(portfolio, current_date)
                portfolio.record_equity(current_date, prices)

            self._event_bus.emit("day_end", date=current_date)

            if current_date in breakpoints_set:
                self._event_bus.emit("breakpoint_hit", date=current_date)

        self._event_bus.emit("run_end", trading_days=len(trading_days))

        result = EngineResult(
            trading_days=len(trading_days),
            start_date=start_date,
            end_date=end_date,
        )
        for agent in agents:
            portfolio = self._portfolios[agent.agent_id]
            result.agent_data[agent.agent_id] = {
                "equity_curve": portfolio.equity_curve,
                "trades": self._trade_histories[agent.agent_id],
            }

        return result

    def _place_order(
        self,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str,
        trade_date: date,
        reasoning: str = "",
    ) -> dict:
        portfolio = self._portfolios.get(agent_id)
        if portfolio is None:
            return {"success": False, "reason": f"Unknown agent: {agent_id}"}

        if self._matching is None:
            return {"success": False, "reason": "No market profile configured"}

        prev_close = self._market_data.get_prev_close(stock_code, trade_date)
        if prev_close is None:
            return {"success": False, "reason": f"No prev_close for {stock_code}"}

        price = self._market_data.get_price(stock_code, trade_date)
        if price is None:
            return {"success": False, "reason": f"No price for {stock_code}"}

        order = Order(
            stock_code=stock_code,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            price=price,
            quantity=quantity,
            trade_date=trade_date,
            stock_name=stock_name,
            reasoning=reasoning,
        )

        result = self._matching.execute(order, portfolio, prev_close)
        if result.success and result.trade:
            self._trade_histories[agent_id].append(result.trade)
        return {
            "success": result.success,
            "reason": result.reason,
            "trade": result.trade,
        }

    def _get_prices_for_portfolio(
        self, portfolio: Portfolio, trade_date: date
    ) -> dict[str, Decimal]:
        prices: dict[str, Decimal] = {}
        for code in portfolio.positions:
            price = self._market_data.get_price(code, trade_date)
            if price is not None:
                prices[code] = price
        return prices
