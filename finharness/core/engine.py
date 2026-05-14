"""BacktestEngine — 回测启动时一次性加载全市场数据，回测过程中纯内存读取。

设计原则：
1. 初始化时全量加载（一次 I/O）
2. 回测过程中零 I/O — 所有数据从内存 dict 查询
3. TradingBus 只是 全局数据 + 日期隔离 的视图
"""

from __future__ import annotations

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
    """Data backend protocol."""

    async def get_daily_bars(self, stock_code: str, start: date, end: date) -> pd.DataFrame: ...
    async def get_stock_list(self) -> list[dict]: ...


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


class MarketData:
    """全市场数据容器 — 回测启动时一次性加载，回测过程中只读。"""

    def __init__(self) -> None:
        self._data: dict[str, pd.DataFrame] = {}
        self._5min_data: dict[str, pd.DataFrame] = {}

    async def load_all(self, provider: DataProvider, start: date, end: date) -> None:
        """一次性加载全市场数据到内存。

        数据源优先级：
        1. ParquetProvider（测试用，从指定目录读多个文件）
        2. MarketDataManager（生产用，单文件 daily.parquet / 5min.parquet）
        """
        from pathlib import Path

        # 路径1：测试/自定义目录（多文件模式）
        if hasattr(provider, '_data_dir'):
            data_dir = Path(provider._data_dir)
            if data_dir.exists() and len(list(data_dir.glob("*.parquet"))) > 0:
                self._load_multi_file_dir(data_dir)
                dir_5min = data_dir.parent / "market_data_5min"
                if dir_5min.exists():
                    self._load_multi_file_dir(dir_5min, is_5min=True)
                return

        # 路径2：单文件缓存（首次从 mootdx 拉取，后续读缓存）
        from finharness.data.market_data_manager import MarketDataManager
        manager = MarketDataManager()

        daily_df = manager.load_daily()
        self._ingest_combined_df(daily_df, is_5min=False)

        if manager.has_5min_cache():
            min5_df = manager.load_5min()
            self._ingest_combined_df(min5_df, is_5min=True)

    def _ingest_combined_df(self, df: pd.DataFrame, is_5min: bool = False) -> None:
        """将合并的 DataFrame（含 stock_code 列）拆分为 per-stock dict。"""
        if df.empty or "stock_code" not in df.columns:
            return
        store = self._5min_data if is_5min else self._data
        for code, group in df.groupby("stock_code"):
            store[code] = group.drop(columns=["stock_code"]).reset_index(drop=True)
        label = "5min" if is_5min else "daily"
        logger.info("%s data ingested: %d stocks", label, len(store))

    def _load_multi_file_dir(self, directory: "Path", is_5min: bool = False) -> None:
        """从多文件目录读取（兼容测试 fixtures）。"""
        from pathlib import Path
        files = list(Path(directory).glob("*.parquet"))
        if not files:
            return
        store = self._5min_data if is_5min else self._data
        for f in files:
            try:
                df = pd.read_parquet(f)
                if "date" in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df["date"]):
                        df["date"] = df["date"].dt.date
                    else:
                        df["date"] = pd.to_datetime(df["date"]).dt.date
                if not df.empty:
                    store[f.stem] = df
            except Exception:
                pass
        label = "5min" if is_5min else "daily"
        logger.info("%s data loaded: %d stocks from %s", label, len(store), directory)

    def get(self, stock_code: str) -> pd.DataFrame:
        return self._data.get(stock_code, pd.DataFrame())

    def all_codes(self) -> list[str]:
        return list(self._data.keys())

    def get_5min(self, stock_code: str) -> pd.DataFrame:
        """获取5分钟线数据（如果已加载）。"""
        return self._5min_data.get(stock_code, pd.DataFrame())

    def load_5min(self, stock_code: str, df: pd.DataFrame) -> None:
        """手动加载5分钟线数据。"""
        self._5min_data[stock_code] = df

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, code: str) -> bool:
        return code in self._data


class TradingBus:
    """交易总线 — 对全局 MarketData 做日期隔离视图 + 交易执行。

    不做任何 I/O，所有数据从内存中的 MarketData 读取。
    """

    def __init__(
        self,
        market_data: MarketData,
        profile: MarketProfile,
        portfolio: Portfolio,
        event_bus: EventBus,
    ) -> None:
        self._market = market_data
        self._profile = profile
        self._portfolio = portfolio
        self._event_bus = event_bus
        self._current_date: date | None = None
        self._traded_today: set[str] = set()
        self.trade_history: list[dict] = []
        self._day_index: int = 0
        self._total_days: int = 0

    @property
    def current_date(self) -> date | None:
        return self._current_date

    @property
    def portfolio(self) -> PortfolioView:
        return PortfolioView(self._portfolio)

    @property
    def market(self) -> MarketData:
        return self._market

    def _set_date(self, d: date) -> None:
        self._current_date = d
        self._traded_today = set()

    def get_daily_bars(self, stock_code: str, days: int = 20) -> pd.DataFrame:
        """获取日K线（严格日期隔离：不含当天）。纯内存读取。"""
        df = self._market.get(stock_code)
        if df.empty:
            return df
        filtered = df[df["date"] < self._current_date]
        return filtered.tail(days)

    def get_5min_bars(self, stock_code: str, target_date: "date | None" = None) -> pd.DataFrame:
        """获取5分钟K线。如果 MarketData 中有5分钟数据则返回，否则返回空。"""
        target = target_date or self._current_date
        df = self._market.get_5min(stock_code)
        if df.empty:
            return df
        if "date" in df.columns:
            return df[df["date"] == target]
        return df

    def get_stock_price(self, stock_code: str) -> dict | None:
        """获取最新价格（前一个交易日的收盘价）。"""
        df = self._market.get(stock_code)
        if df.empty:
            return None
        filtered = df[df["date"] < self._current_date]
        if filtered.empty:
            return None
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2] if len(filtered) >= 2 else last
        prev_close = float(prev["close"])
        change_pct = ((float(last["close"]) - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        return {
            "stock_code": stock_code,
            "date": str(last["date"]),
            "close": round(float(last["close"]), 2),
            "change_pct": round(change_pct, 2),
        }

    def get_execution_price(self, stock_code: str, window: str = "open") -> Decimal | None:
        """获取当天成交价。window='open'=开盘价, 'close'=收盘价。"""
        df = self._market.get(stock_code)
        if df.empty:
            return None
        today = df[df["date"] == self._current_date]
        if today.empty:
            return None
        row = today.iloc[0]
        col = "open" if window == "open" else "close"
        return Decimal(str(row[col])).quantize(TWO_PLACES)

    def place_order(
        self,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str = "",
        reasoning: str = "",
        window: str = "open",
    ) -> dict:
        """执行交易订单。唯一的下单入口 — tool handler 和 simple agent 都调用此方法。"""
        if self._current_date is None:
            return {"success": False, "error": "交易日未设置"}
        if stock_code in self._traded_today:
            return {"success": False, "error": f"{stock_code} 今天已交易过"}

        price = self.get_execution_price(stock_code, window)
        if price is None:
            return {"success": False, "error": f"{stock_code} 无法获取成交价"}

        # 涨跌停检查
        df = self._market.get(stock_code)
        if not df.empty:
            prev_data = df[df["date"] < self._current_date]
            if not prev_data.empty:
                prev_close = Decimal(str(prev_data.iloc[-1]["close"])).quantize(TWO_PLACES)
                limit_up, limit_down = self._profile.price_limits(stock_code, prev_close)
                if price >= limit_up:
                    return {"success": False, "error": f"{stock_code} 涨停 (涨停价 {limit_up})"}
                if price <= limit_down:
                    return {"success": False, "error": f"{stock_code} 跌停 (跌停价 {limit_down})"}

        try:
            if side == "buy":
                qty = self._profile.round_lot(quantity)
                if qty <= 0:
                    return {"success": False, "error": f"买入数量 {quantity} 不足1手（100股）"}
                trade = self._portfolio.buy(stock_code, stock_name or stock_code, price, qty, self._current_date)
            elif side == "sell":
                pos = self._portfolio.positions.get(stock_code)
                if pos is None:
                    return {"success": False, "error": f"未持有 {stock_code}"}
                sellable = pos.sellable_quantity(self._current_date)
                qty = min(quantity, sellable) if quantity > 0 else sellable
                if qty <= 0:
                    return {"success": False, "error": f"{stock_code} T+1限制，今日无可卖数量"}
                avg_cost = pos.avg_cost
                trade = self._portfolio.sell(stock_code, price, qty, self._current_date)
                trade["pnl"] = float(trade["net_income"]) - float(avg_cost * qty)
            else:
                return {"success": False, "error": f"无效操作: {side}"}
        except ValueError as e:
            return {"success": False, "error": str(e)}

        trade["signal_reasoning"] = reasoning
        trade["date"] = str(self._current_date)
        self._traded_today.add(stock_code)
        self.trade_history.append(trade)
        self._event_bus.emit("order_placed", trade=trade, agent_id=agent_id)
        return {"success": True, "trade": trade}


class BacktestEngine:
    """回测引擎：启动时全量加载数据，逐日驱动 Agent。"""

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

        # ===== 一次性全量加载全市场数据 =====
        market_data = MarketData()
        if self._data_provider:
            await market_data.load_all(self._data_provider, start_date, end_date)

        # 为每个 agent 创建独立 portfolio + bus（共享同一份 market_data）
        buses: dict[str, TradingBus] = {}
        portfolios: dict[str, Portfolio] = {}

        for agent in agents:
            portfolio = Portfolio(self._config.initial_cash)
            portfolios[agent.agent_id] = portfolio
            buses[agent.agent_id] = TradingBus(
                market_data=market_data,
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

                # 日终：用收盘价记录权益
                portfolio = portfolios[agent.agent_id]
                prices: dict[str, Decimal] = {}
                for code in portfolio.positions:
                    p = bus.get_execution_price(code, "close")
                    if p:
                        prices[code] = p
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

    @staticmethod
    def _check_knowledge_cutoff(end_date: date) -> None:
        KNOWN_CUTOFFS = {
            "deepseek-chat": date(2024, 7, 1),
            "gpt-4o": date(2024, 10, 1),
            "gpt-4-turbo": date(2024, 4, 1),
            "claude-3.5-sonnet": date(2024, 4, 1),
        }
        for model, cutoff in KNOWN_CUTOFFS.items():
            if end_date > cutoff:
                logger.warning(
                    "LLM_KNOWLEDGE_CUTOFF_WARNING: 回测结束日 %s 超过 %s 的知识截止日 %s",
                    end_date, model, cutoff,
                )


# Legacy alias
MarketDataProvider = DataProvider
