"""BacktestEngine — TradingBus 模式: Agent 自主查询一切数据。

直接从源项目 backend/arena/trading_bus.py 迁移设计。
Engine 提供数据服务 → Agent 自主查询和操作。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol

import pandas as pd

from finharness.core.calendar import TradingCalendar
from finharness.core.events import EventBus
from finharness.core.market_profile import AShareProfile, MarketProfile
from finharness.core.portfolio import Portfolio, PortfolioView

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


class DataProvider(Protocol):
    """Data backend for the engine."""

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame: ...


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


class TradingBus:
    """交易总线 — Agent 通过此对象获取数据和执行交易。

    Agent 在 on_day(bus, date) 中调用 bus 的方法。
    """

    def __init__(
        self,
        data_provider: DataProvider | None,
        profile: MarketProfile,
        portfolio: Portfolio,
        event_bus: EventBus,
    ) -> None:
        self._data = data_provider
        self._profile = profile
        self._portfolio = portfolio
        self._event_bus = event_bus
        self._current_date: date | None = None
        self._daily_cache: dict[str, pd.DataFrame] = {}
        self._traded_today: set[str] = set()
        self.trade_history: list[dict] = []

    @property
    def current_date(self) -> date | None:
        return self._current_date

    @property
    def portfolio(self) -> PortfolioView:
        return PortfolioView(self._portfolio)

    def _set_date(self, d: date) -> None:
        self._current_date = d
        self._traded_today = set()

    async def get_daily_bars(self, stock_code: str, days: int = 20) -> pd.DataFrame:
        """获取日K线（严格日期隔离：不含当天）。"""
        df = await self._ensure_daily(stock_code)
        if df.empty:
            return df
        filtered = df[df["date"] < self._current_date]
        return filtered.tail(days)

    async def get_stock_price(self, stock_code: str) -> dict | None:
        """获取最新价格（截止到 current_date 前一天的收盘价）。"""
        df = await self._ensure_daily(stock_code)
        if df.empty:
            return None
        filtered = df[df["date"] < self._current_date]
        if filtered.empty:
            return None
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2] if len(filtered) >= 2 else last
        change_pct = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100
        return {
            "stock_code": stock_code,
            "date": str(last["date"]),
            "close": round(float(last["close"]), 2),
            "change_pct": round(change_pct, 2),
        }

    async def get_execution_price(self, stock_code: str, window: str = "open") -> Decimal | None:
        """获取成交价格。window='open'=开盘价, 'close'=收盘价。"""
        df = await self._ensure_daily(stock_code)
        if df.empty:
            return None
        today = df[df["date"] == self._current_date]
        if today.empty:
            return None
        row = today.iloc[0]
        col = "open" if window == "open" else "close"
        return Decimal(str(row[col])).quantize(TWO_PLACES)

    async def place_order(
        self,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str = "",
        reasoning: str = "",
    ) -> dict:
        """执行交易订单。"""
        if stock_code in self._traded_today:
            return {"success": False, "error": f"{stock_code} 今天已交易过"}

        price = await self.get_execution_price(stock_code, "open")
        if price is None:
            return {"success": False, "error": f"{stock_code} 无法获取成交价"}

        # 涨跌停检查
        df = await self._ensure_daily(stock_code)
        if not df.empty:
            prev_data = df[df["date"] < self._current_date]
            if not prev_data.empty:
                prev_close = Decimal(str(prev_data.iloc[-1]["close"])).quantize(TWO_PLACES)
                limit_up, limit_down = self._profile.price_limits(stock_code, prev_close)
                if price >= limit_up:
                    return {"success": False, "error": f"{stock_code} 涨停"}
                if price <= limit_down:
                    return {"success": False, "error": f"{stock_code} 跌停"}

        try:
            if side == "buy":
                qty = self._profile.round_lot(quantity)
                if qty <= 0:
                    return {"success": False, "error": f"买入数量不足1手"}
                trade = self._portfolio.buy(stock_code, stock_name or stock_code, price, qty, self._current_date)
            elif side == "sell":
                pos = self._portfolio.positions.get(stock_code)
                if pos is None:
                    return {"success": False, "error": f"未持有 {stock_code}"}
                sellable = pos.sellable_quantity(self._current_date)
                qty = min(quantity, sellable) if quantity > 0 else sellable
                if qty <= 0:
                    return {"success": False, "error": f"{stock_code} T+1限制"}
                avg_cost = pos.avg_cost
                trade = self._portfolio.sell(stock_code, price, qty, self._current_date)
                trade["pnl"] = float(trade["net_income"]) - float(avg_cost * qty)
            else:
                return {"success": False, "error": f"无效操作: {side}"}
        except ValueError as e:
            return {"success": False, "error": str(e)}

        trade["signal_reasoning"] = reasoning
        self._traded_today.add(stock_code)
        self.trade_history.append(trade)
        self._event_bus.emit("order_placed", trade=trade, agent_id=agent_id)
        return {"success": True, "trade": trade}

    async def _ensure_daily(self, stock_code: str) -> pd.DataFrame:
        if stock_code in self._daily_cache:
            return self._daily_cache[stock_code]
        if self._data is None:
            return pd.DataFrame()
        # Fetch a wide range to cover the entire backtest + history
        start = self._current_date - timedelta(days=365)
        end = self._current_date + timedelta(days=365)
        df = await self._data.get_daily_bars(stock_code, start, end)
        if df is not None and not df.empty:
            self._daily_cache[stock_code] = df
            return df
        return pd.DataFrame()


class BacktestEngine:
    """Core engine: progresses through trading days, dispatches agents."""

    def __init__(
        self,
        config: EngineConfig,
        data_provider: DataProvider | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._data_provider = data_provider
        self._event_bus = event_bus or EventBus()
        self._profile = config.profile or AShareProfile()
        self._calendar = config.calendar or TradingCalendar()

    async def run(
        self,
        agents: list[Any],
        start_date: date,
        end_date: date,
        breakpoints: list[date] | None = None,
        warmup_days: int = 0,
    ) -> EngineResult:
        breakpoints_set = set(breakpoints) if breakpoints else set()

        if warmup_days > 0:
            warmup_start = start_date - timedelta(days=int(warmup_days * 1.5))
            all_days = self._calendar.get_trading_days(warmup_start, end_date)
            trading_days = [d for d in all_days if d >= start_date]
        else:
            trading_days = self._calendar.get_trading_days(start_date, end_date)

        # 为每个 agent 创建独立 portfolio + bus
        buses: dict[str, TradingBus] = {}
        portfolios: dict[str, Portfolio] = {}
        trade_histories: dict[str, list[dict]] = {}

        for agent in agents:
            portfolio = Portfolio(self._config.initial_cash)
            portfolios[agent.agent_id] = portfolio
            trade_histories[agent.agent_id] = []
            buses[agent.agent_id] = TradingBus(
                data_provider=self._data_provider,
                profile=self._profile,
                portfolio=portfolio,
                event_bus=self._event_bus,
            )

        self._check_knowledge_cutoff(end_date)
        self._event_bus.emit("run_start", start_date=start_date, end_date=end_date)

        for day_idx, current_date in enumerate(trading_days):
            self._event_bus.emit("day_start", date=current_date)

            for agent in agents:
                bus = buses[agent.agent_id]
                bus._set_date(current_date)
                bus._day_index = day_idx
                bus._total_days = len(trading_days)
                try:
                    await agent.on_day(bus, current_date)
                except Exception:
                    logger.exception("Agent %s error on %s", agent.agent_id, current_date)

                # 记录权益
                portfolio = portfolios[agent.agent_id]
                prices = await self._get_prices(portfolio, current_date, bus)
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
            portfolio = portfolios[agent.agent_id]
            bus = buses[agent.agent_id]
            result.agent_data[agent.agent_id] = {
                "equity_curve": portfolio.equity_curve,
                "trades": bus.trade_history,
            }

        return result

    async def _get_prices(self, portfolio: Portfolio, trade_date: date, bus: TradingBus) -> dict[str, Decimal]:
        prices: dict[str, Decimal] = {}
        for code in portfolio.positions:
            price = await bus.get_execution_price(code, "close")
            if price:
                prices[code] = price
        return prices

    @staticmethod
    def _check_knowledge_cutoff(end_date: date) -> None:
        """Warn if backtest period exceeds known LLM knowledge cutoff dates."""
        KNOWN_CUTOFFS = {
            "deepseek-chat": date(2024, 7, 1),
            "gpt-4o": date(2024, 10, 1),
            "gpt-4-turbo": date(2024, 4, 1),
            "claude-3.5-sonnet": date(2024, 4, 1),
        }
        for model, cutoff in KNOWN_CUTOFFS.items():
            if end_date > cutoff:
                logger.warning(
                    "LLM_KNOWLEDGE_CUTOFF_WARNING: 回测结束日 %s 超过 %s 的知识截止日 %s — "
                    "LLM 可能「知道未来」，回测结果可能偏乐观",
                    end_date, model, cutoff,
                )


# Legacy compatibility aliases
MarketDataProvider = DataProvider
