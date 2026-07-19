"""BacktestEngine — 回测启动时一次性加载全市场数据，回测过程中纯内存读取。

设计原则：
1. 初始化时全量加载（一次 I/O）
2. 回测过程中零 I/O — 所有数据从内存 dict 查询
3. TradingBus 只是 全局数据 + 日期隔离 的视图
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from traderharness.core.calendar import TradingCalendar
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile, MarketProfile
from traderharness.core.portfolio import Portfolio, PortfolioView
from traderharness.data.dividend_manager import DividendManager
from traderharness.data.news_data_manager import NewsDataManager

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
    dataset_dir: str | None = None
    mask_entities: bool = False
    entity_mask_seed: int | str = 0
    cancel_check: Callable[[], bool] | None = None


@dataclass
class EngineResult:
    trading_days: int = 0
    start_date: date | None = None
    end_date: date | None = None
    agent_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_agents: dict[str, str] = field(default_factory=dict)


class AgentExecutionError(RuntimeError):
    """Raised when one or more agents raise during ``BacktestEngine.run``.

    The environment must fail closed instead of silently logging and
    continuing as if the run had succeeded. The partial ``EngineResult``
    (with per-agent failure reasons in ``result.failed_agents`` and
    ``result.agent_data[agent_id]["error"]``) is attached so callers that
    want to inspect or persist a failed run can still do so.
    """

    def __init__(self, message: str, result: EngineResult) -> None:
        super().__init__(message)
        self.result = result


class MarketData:
    """全市场数据容器 — 回测启动时一次性加载，回测过程中只读。"""

    def __init__(self) -> None:
        self._data: dict[str, pd.DataFrame] = {}
        self._5min_data: dict[str, pd.DataFrame] = {}

    async def load_all(self, provider: DataProvider, start: date, end: date) -> None:
        """一次性加载全市场数据到内存。

        数据源优先级：
        1. ParquetProvider（测试用，从指定目录读多个文件）
        2. Simple providers (test/custom) — use get_daily_bars interface
        3. MarketDataManager（生产用，单文件 daily.parquet / 5min.parquet）
        """
        from pathlib import Path

        # 路径1：测试/自定义目录（多文件模式）
        if hasattr(provider, "_data_dir"):
            data_dir = Path(provider._data_dir)
            if data_dir.exists() and len(list(data_dir.glob("*.parquet"))) > 0:
                self._load_multi_file_dir(data_dir)
                dir_5min = data_dir.parent / "market_data_5min"
                if dir_5min.exists():
                    self._load_multi_file_dir(dir_5min, is_5min=True)
                return

        # 路径2：Simple test providers without _data_dir and without _use_manager flag
        if not getattr(provider, "_use_manager", False):
            stocks = await provider.get_stock_list()
            has_5min_hook = hasattr(provider, "get_5min_bars")
            for stock_info in stocks:
                code = stock_info if isinstance(stock_info, str) else stock_info.get("code", "")
                if not code:
                    continue
                df = await provider.get_daily_bars(code, start, end)
                if df is not None and not df.empty:
                    if "date" in df.columns:
                        if pd.api.types.is_datetime64_any_dtype(df["date"]):
                            df["date"] = df["date"].dt.date
                        elif not all(isinstance(d, date) for d in df["date"].head(1)):
                            df["date"] = pd.to_datetime(df["date"]).dt.date
                    self._data[code] = df
                # Optional: providers may also expose 5-minute bars (test/custom
                # fixtures). Production loading always goes through path 3 below.
                if has_5min_hook:
                    min5_df = await provider.get_5min_bars(code, start, end)
                    if min5_df is not None and not min5_df.empty:
                        if "date" in min5_df.columns and not all(
                            isinstance(d, date) for d in min5_df["date"].head(1)
                        ):
                            min5_df["date"] = pd.to_datetime(min5_df["date"]).dt.date
                        self._5min_data[code] = min5_df
            if self._data:
                logger.info("Loaded %d stocks via provider interface", len(self._data))
                return

        # 路径3：单文件缓存（生产用）
        from traderharness.data.market_data_manager import MarketDataManager

        manager = MarketDataManager()

        daily_df = manager.load_daily()
        self._ingest_combined_df(daily_df, is_5min=False)

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

    def _load_multi_file_dir(self, directory: Path, is_5min: bool = False) -> None:
        """从多文件目录读取（兼容测试 fixtures）。"""
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
        self._news_manager: NewsDataManager | None = None
        self._corporate_actions_today: list[dict] = []

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
        self._corporate_actions_today = []

    def get_daily_bars(self, stock_code: str, days: int = 20) -> pd.DataFrame:
        """获取日K线（严格日期隔离：不含当天）。纯内存读取。"""
        df = self._market.get(stock_code)
        if df.empty:
            return df
        filtered = df[df["date"] < self._current_date]
        return filtered.tail(days)

    def get_5min_bars(self, stock_code: str, target_date: date | None = None) -> pd.DataFrame:
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
        change_pct = (
            ((float(last["close"]) - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        )
        return {
            "stock_code": stock_code,
            "date": str(last["date"]),
            "close": round(float(last["close"]), 2),
            "change_pct": round(change_pct, 2),
        }

    def get_execution_price(self, stock_code: str, window: str = "open") -> Decimal | None:
        """获取当天成交价 — 用子窗口最后一根5分钟bar的收盘价撮合。

        window 值:
          "open_1": 9:35~9:50 最后bar close
          "open_2": 9:55~10:00 最后bar close (or "open" legacy)
          "close_1": 14:35~14:50 最后bar close
          "close_2": 14:55~15:00 最后bar close (or "close" legacy)

        撮合公平：只允许用当前子窗口内已经"发生过"的5分钟bar成交。
        如果5分钟数据不可用，返回 None —— 绝不回退到日线 open/close，
        否则等价于让 Agent 看完整交易日再挑一个更优价格成交，破坏撮合公平性。
        """
        bars_5m = self.get_5min_bars(stock_code)
        if bars_5m.empty or "datetime" not in bars_5m.columns:
            return None

        minutes = bars_5m["datetime"].dt.hour * 60 + bars_5m["datetime"].dt.minute

        time_ranges = {
            "open_1": (9 * 60 + 35, 9 * 60 + 50),
            "open_2": (9 * 60 + 55, 10 * 60),
            "open": (9 * 60 + 35, 10 * 60),
            "close_1": (14 * 60 + 35, 14 * 60 + 50),
            "close_2": (14 * 60 + 55, 15 * 60),
            "close": (14 * 60 + 35, 15 * 60),
        }

        t_range = time_ranges.get(window, time_ranges["open"])
        window_bars = bars_5m[(minutes >= t_range[0]) & (minutes <= t_range[1])]

        if window_bars.empty:
            return None
        return Decimal(str(window_bars.iloc[-1]["close"])).quantize(TWO_PLACES)

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
            return {
                "success": False,
                "error": (
                    f"{stock_code} 当前子窗口({window})无5分钟K线数据，无法确定成交价。"
                    "请等待下一交易窗口再下单，或确认该股票当天是否停牌/无行情。"
                ),
            }

        # 涨跌停检查
        df = self._market.get(stock_code)
        if not df.empty:
            prev_data = df[df["date"] < self._current_date]
            if not prev_data.empty:
                prev_close = Decimal(str(prev_data.iloc[-1]["close"])).quantize(TWO_PLACES)
                limit_up, limit_down = self._profile.price_limits(stock_code, prev_close)
                if price >= limit_up and side == "buy":
                    return {
                        "success": False,
                        "error": f"{stock_code} 涨停封板，无法买入 (涨停价 {limit_up})",
                    }
                if price <= limit_down and side == "sell":
                    return {
                        "success": False,
                        "error": f"{stock_code} 跌停封板，无法卖出 (跌停价 {limit_down})",
                    }

        try:
            if side == "buy":
                qty = self._profile.round_lot(quantity)
                if qty <= 0:
                    return {"success": False, "error": f"买入数量 {quantity} 不足1手（100股）"}
                trade = self._portfolio.buy(
                    stock_code, stock_name or stock_code, price, qty, self._current_date
                )
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
        trade["window"] = window
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
        self._entity_masker = None

        dataset_dir = Path(config.dataset_dir) if config.dataset_dir else None
        self._dividend_manager = DividendManager(dataset_dir=dataset_dir)
        self._news_manager = NewsDataManager(
            dataset_dir=dataset_dir,
            templated=config.mask_entities,
        )

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

        # ===== 一次性加载市场数据（按回测时间段过滤，大幅减少内存和启动时间）=====
        # warmup: 加载回测开始前 120 个交易日的数据（Agent 需要看历史 K 线）
        warmup_calendar_days = 180  # ~120 trading days
        data_start = start_date - timedelta(days=warmup_calendar_days)

        market_data = MarketData()
        if self._data_provider:
            await market_data.load_all(self._data_provider, data_start, end_date)
        else:
            from traderharness.data.market_data_manager import MarketDataManager

            manager = MarketDataManager()
            daily_df = manager.load_daily(start_date=data_start, end_date=end_date)
            market_data._ingest_combined_df(daily_df, is_5min=False)
            if manager.has_5min_cache():
                min5_df = manager.load_5min(start_date=start_date, end_date=end_date)
                market_data._ingest_combined_df(min5_df, is_5min=True)

        # Load news, dividend, and fundamentals data.
        # Skip when a test provider has no dataset directory.
        if self._config.dataset_dir or not self._data_provider:
            self._news_manager.load(start_date=start_date, end_date=end_date)
            self._dividend_manager.load()
        else:
            # Test mode with simple provider — don't load heavy auxiliary data
            pass

        # Load fundamentals, business segments, valuation
        from pathlib import Path

        from traderharness.paths import dataset_dir as default_dataset_dir

        if self._config.dataset_dir:
            dataset_dir = Path(self._config.dataset_dir)
        elif not self._data_provider:
            dataset_dir = default_dataset_dir()
        else:
            # Test mode with simple provider — skip heavy data loading
            dataset_dir = None
        if dataset_dir is None:
            self._fundamentals_df = pd.DataFrame()
            self._business_segments_df = pd.DataFrame()
            self._valuation_df = pd.DataFrame()
        else:
            fundamentals_path = dataset_dir / "fundamentals.parquet"
            self._fundamentals_df = pd.DataFrame()
            if fundamentals_path.exists():
                self._fundamentals_df = pd.read_parquet(fundamentals_path)
                logger.info(
                    "Fundamentals loaded: %d rows, %d stocks",
                    len(self._fundamentals_df),
                    self._fundamentals_df["stock_code"].nunique()
                    if "stock_code" in self._fundamentals_df.columns
                    else 0,
                )

            segments_path = dataset_dir / "business_segments.parquet"
            self._business_segments_df = pd.DataFrame()
            if segments_path.exists():
                self._business_segments_df = pd.read_parquet(segments_path)
                logger.info(
                    "Business segments loaded: %d rows, %d stocks",
                    len(self._business_segments_df),
                    self._business_segments_df["stock_code"].nunique()
                    if "stock_code" in self._business_segments_df.columns
                    else 0,
                )

            valuation_path = dataset_dir / "valuation.parquet"
            self._valuation_df = pd.DataFrame()
            if valuation_path.exists():
                self._valuation_df = pd.read_parquet(valuation_path)
                if "date" in self._valuation_df.columns:
                    if pd.api.types.is_datetime64_any_dtype(self._valuation_df["date"]):
                        self._valuation_df["date"] = self._valuation_df["date"].dt.date
                    else:
                        self._valuation_df["date"] = pd.to_datetime(
                            self._valuation_df["date"]
                        ).dt.date
                logger.info(
                    "Valuation loaded: %d rows, %d stocks",
                    len(self._valuation_df),
                    self._valuation_df["stock_code"].nunique()
                    if "stock_code" in self._valuation_df.columns
                    else 0,
                )

        # 为每个 agent 创建独立 portfolio + bus（共享同一份 market_data）
        buses: dict[str, TradingBus] = {}
        portfolios: dict[str, Portfolio] = {}
        entity_masker = None
        if self._config.mask_entities:
            from traderharness.core.entity_masking import EntityMasker
            from traderharness.data.entity_templates import build_alias_map
            from traderharness.data.stock_registry_loader import get_stock_registry
            from traderharness.paths import dataset_dir

            registry = get_stock_registry()
            codes = market_data.all_codes()
            names = {code: registry.get(code, {}).get("name", code) for code in codes}
            # Egress masking keeps using the loaded (possibly templated/windowed)
            # announcement frame so agent-visible prompts stay stable for replay.
            aliases: dict[str, set[str]] = {}
            announcements = self._news_manager.announcements
            if (
                announcements is not None
                and not announcements.empty
                and {"stock_code", "stock_name"}.issubset(announcements.columns)
            ):
                for code, group in announcements.groupby("stock_code"):
                    aliases[str(code)] = {
                        str(value).strip()
                        for value in group["stock_name"].dropna().unique()
                        if str(value).strip()
                    }
            # Output scrubbing uses the canonical full announcement table so
            # historical names (四川金顶 while the registry says ST金顶) are still
            # removed when the model emits them from prior knowledge.
            announcements_path = dataset_dir() / "announcements.parquet"
            canonical_announcements = (
                pd.read_parquet(announcements_path, columns=["stock_code", "stock_name"])
                if announcements_path.exists()
                else None
            )
            entity_masker = EntityMasker(
                codes,
                names=names,
                aliases=aliases,
                sanitize_aliases=build_alias_map(registry, canonical_announcements),
                seed=self._config.entity_mask_seed,
            )
        self._entity_masker = entity_masker

        for agent in agents:
            portfolio = Portfolio(self._config.initial_cash)
            portfolios[agent.agent_id] = portfolio
            buses[agent.agent_id] = TradingBus(
                market_data=market_data,
                profile=self._profile,
                portfolio=portfolio,
                event_bus=self._event_bus,
            )
            buses[agent.agent_id]._entity_masker = entity_masker

        self._check_knowledge_cutoff(end_date)
        self._event_bus.emit(
            "run_start",
            start_date=start_date,
            end_date=end_date,
            total_days=len(trading_days),
        )

        completed_days = 0
        cancelled = False
        agent_errors: dict[str, BaseException] = {}
        for day_idx, current_date in enumerate(trading_days):
            if self._config.cancel_check is not None and self._config.cancel_check():
                cancelled = True
                break
            self._event_bus.emit("day_start", date=current_date)

            # Phase 1: Set date + attach news manager for all agents
            for agent in agents:
                bus = buses[agent.agent_id]
                bus._set_date(current_date)
                bus._day_index = day_idx
                bus._total_days = len(trading_days)
                bus._news_manager = self._news_manager
                bus._fundamentals_df = self._fundamentals_df
                bus._business_segments_df = self._business_segments_df
                bus._valuation_df = self._valuation_df

            # Phase 2: Corporate actions (after _set_date, before trading)
            for agent in agents:
                portfolio = portfolios[agent.agent_id]
                actions = self._dividend_manager.process_day(current_date, portfolio)
                if actions:
                    buses[agent.agent_id]._corporate_actions_today = actions

            # Phase 3: run independent agents. Each owns a separate
            # Portfolio/TradingBus while sharing market frames by reference.
            # Execution is sequential within the day so Agent-facing tool
            # results and morning briefs stay fingerprint-stable for replay:
            # concurrent asyncio.gather previously raced on shared DataFrame
            # views and made multi-agent cassettes unreproducible.
            for agent in agents:
                bus = buses[agent.agent_id]
                try:
                    await agent.on_day(bus, current_date)
                except Exception as exc:
                    logger.exception("Agent %s error on %s", agent.agent_id, current_date)
                    # Fail closed: never let an agent exception vanish silently.
                    # Keep the first failure per agent (most informative root
                    # cause); remaining agents still run independently.
                    agent_errors.setdefault(agent.agent_id, exc)

            # 日终：用收盘价记录权益
            day_equity: dict[str, dict[str, float]] = {}
            initial_cash = float(self._config.initial_cash)
            for agent in agents:
                bus = buses[agent.agent_id]
                portfolio = portfolios[agent.agent_id]
                prices: dict[str, Decimal] = {}
                for code in portfolio.positions:
                    p = bus.get_execution_price(code, "close")
                    if p:
                        prices[code] = p
                portfolio.record_equity(current_date, prices)
                equity = float(portfolio.equity_curve[-1][1])
                day_equity[agent.agent_id] = {
                    "equity": equity,
                    "return_pct": (equity - initial_cash) / initial_cash * 100
                    if initial_cash > 0
                    else 0.0,
                }

            self._event_bus.emit(
                "day_end",
                date=current_date,
                day_index=day_idx,
                total_days=len(trading_days),
                equity=day_equity,
            )
            completed_days += 1

            if current_date in breakpoints_set:
                self._event_bus.emit("breakpoint_hit", date=current_date)

        self._event_bus.emit(
            "run_end",
            trading_days=completed_days,
            cancelled=cancelled,
        )

        result = EngineResult(
            trading_days=completed_days,
            start_date=start_date,
            end_date=end_date,
        )
        for agent in agents:
            portfolio = portfolios[agent.agent_id]
            bus = buses[agent.agent_id]
            agent_result = {
                "equity_curve": portfolio.equity_curve,
                "trades": bus.trade_history,
            }
            # Include trajectory if available
            if hasattr(agent, "trajectory") and agent.trajectory:
                traj = agent.trajectory
                agent_result["trajectory"] = {
                    "days": [
                        {
                            "date": str(d.date),
                            "observation": d.observation,
                            "actions": d.actions,
                            "reward": d.reward,
                        }
                        for d in traj.day_records
                    ],
                    "steps": [
                        {
                            "date": str(s.date),
                            "step": s.step,
                            "type": s.type,
                            "data": s.data,
                        }
                        for s in traj.step_records
                    ],
                }
            exc = agent_errors.get(agent.agent_id)
            if exc is not None:
                agent_result["error"] = f"{type(exc).__name__}: {exc}"
                result.failed_agents[agent.agent_id] = agent_result["error"]
            result.agent_data[agent.agent_id] = agent_result

        if agent_errors:
            first_agent_id, first_exc = next(iter(agent_errors.items()))
            raise AgentExecutionError(
                f"{len(agent_errors)} agent(s) failed during backtest; "
                f"first failure ({first_agent_id}): {type(first_exc).__name__}: {first_exc}",
                result=result,
            ) from first_exc

        return result

    @staticmethod
    def _check_knowledge_cutoff(end_date: date) -> None:
        known_cutoffs = {
            "deepseek-chat": date(2024, 7, 1),
            "gpt-4o": date(2024, 10, 1),
            "gpt-4-turbo": date(2024, 4, 1),
            "claude-3.5-sonnet": date(2024, 4, 1),
        }
        for model, cutoff in known_cutoffs.items():
            if end_date > cutoff:
                logger.warning(
                    "LLM_KNOWLEDGE_CUTOFF_WARNING: 回测结束日 %s 超过 %s 的知识截止日 %s",
                    end_date,
                    model,
                    cutoff,
                )


# Legacy alias
MarketDataProvider = DataProvider
