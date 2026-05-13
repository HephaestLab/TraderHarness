"""Real data integration tests — 314 stocks, full market, no mocks.

Uses parquet data exported from source project's market_cache.db.
All tests run on real A-share data (2024-01 to 2026-05).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from finharness.core.env import TradingEnv, EnvConfig
from finharness.core.events import EventBus
from finharness.data.providers.parquet import ParquetProvider
from finharness.metrics.performance import calculate_metrics
from finharness.metrics.comparison import compare_vs_benchmark
from finharness.tools.registry import ToolContext
from finharness.tools.market import GET_KLINE, GET_STOCK_PRICE
from finharness.tools.trading import PLACE_ORDER
from finharness.tools.analysis import SCREEN_STOCKS, GET_MARKET_OVERVIEW
from finharness.core.portfolio import Portfolio

DATA_DIR = Path(__file__).parent.parent / "fixtures" / "market_data"


@pytest.fixture
def provider():
    return ParquetProvider(DATA_DIR)


@pytest.fixture
def env_2024h1(provider):
    return TradingEnv(
        config=EnvConfig(
            start_date=date(2024, 3, 1),
            end_date=date(2024, 9, 30),
            initial_cash=Decimal("1000000"),
        ),
        data_provider=provider,
    )


# ============================================================
# Test 1: Full data availability — all 314 stocks loadable
# ============================================================

class TestDataAvailability:
    @pytest.mark.asyncio
    async def test_all_stocks_available(self, provider):
        stocks = await provider.get_stock_list()
        assert len(stocks) >= 5000, f"Expected 5000+ stocks (full A-share market), got {len(stocks)}"

    @pytest.mark.asyncio
    async def test_moutai_has_full_history(self, provider):
        df = await provider.get_daily_bars("600519", date(2024, 1, 1), date(2026, 12, 31))
        assert len(df) > 100, f"Expected 100+ days for 600519, got {len(df)}"

    @pytest.mark.asyncio
    async def test_multiple_stocks_have_data(self, provider):
        for code in ["000001", "300750", "601318", "000858"]:
            df = await provider.get_daily_bars(code, date(2024, 1, 1), date(2024, 12, 31))
            assert len(df) > 100, f"{code} has only {len(df)} days"


# ============================================================
# Test 2: BuyAndHold on Moutai — full period real data
# ============================================================

class TestBuyAndHoldReal:
    def test_moutai_buy_and_hold_6_months(self, env_2024h1):
        class MoutaiBuyHold:
            agent_id = "moutai_bh"
            name = "MoutaiBuyHold"
            _bought = False

            async def on_day(self, bus, current_date):
                if not self._bought:
                    r = await bus.place_order(agent_id="moutai_bh", stock_code="600519", side="buy", quantity=100)
                    if r.get("success"):
                        self._bought = True

        agent = MoutaiBuyHold()
        result = env_2024h1.run(agent)

        equity = result.agent_data["moutai_bh"]["equity_curve"]
        trades = result.agent_data["moutai_bh"]["trades"]
        metrics = calculate_metrics(equity, Decimal("1000000"), trades)

        assert metrics.trading_days > 100
        assert metrics.final_value != 1000000.0  # price moved
        assert agent._bought is True
        assert len(trades) == 1  # only bought once


# ============================================================
# Test 3: Multi-stock portfolio with round-trip trades
# ============================================================

class TestMultiStockPortfolio:
    def test_buy_3_stocks_sell_later(self, env_2024h1):
        class MultiTrader:
            agent_id = "multi"
            name = "MultiTrader"
            _day = 0

            async def on_day(self, bus, current_date):
                self._day += 1
                if self._day == 2:
                    await bus.place_order(agent_id="multi", stock_code="600519", side="buy", quantity=100)
                    await bus.place_order(agent_id="multi", stock_code="000001", side="buy", quantity=1000)
                    await bus.place_order(agent_id="multi", stock_code="300750", side="buy", quantity=100)
                if self._day == 60:
                    await bus.place_order(agent_id="multi", stock_code="600519", side="sell", quantity=100)
                    await bus.place_order(agent_id="multi", stock_code="000001", side="sell", quantity=1000)
                    await bus.place_order(agent_id="multi", stock_code="300750", side="sell", quantity=100)

        result = env_2024h1.run(MultiTrader())
        trades = result.agent_data["multi"]["trades"]
        equity = result.agent_data["multi"]["equity_curve"]

        buy_trades = [t for t in trades if t["action"] == "buy"]
        sell_trades = [t for t in trades if t["action"] == "sell"]
        assert len(buy_trades) == 3
        assert len(sell_trades) == 3

        metrics = calculate_metrics(equity, Decimal("1000000"), trades)
        assert metrics.total_trades == 3
        assert metrics.trading_days > 100


# ============================================================
# Test 4: T+1 enforcement with real data
# ============================================================

class TestTPlus1Real:
    def test_cannot_sell_same_day(self, env_2024h1):
        class SameDaySeller:
            agent_id = "t1_test"
            name = "T1Test"
            sell_results = []
            _day = 0

            async def on_day(self, bus, current_date):
                self._day += 1
                if self._day == 2:
                    await bus.place_order(agent_id="t1_test", stock_code="600519", side="buy", quantity=100)
                    r = await bus.place_order(agent_id="t1_test", stock_code="600519", side="sell", quantity=100)
                    self.sell_results.append(r)

        agent = SameDaySeller()
        env_2024h1.run(agent)
        assert agent.sell_results[0]["success"] is False


# ============================================================
# Test 5: Event system fires with real data
# ============================================================

class TestEventsReal:
    def test_events_fire_during_backtest(self, provider):
        events = []
        bus = EventBus()
        bus.on("run_start", lambda **kw: events.append("run_start"))
        bus.on("run_end", lambda **kw: events.append("run_end"))
        bus.on("order_placed", lambda **kw: events.append("order_placed"))

        class Buyer:
            agent_id = "evt"
            name = "Evt"
            _bought = False
            async def on_day(self, b, d):
                if not self._bought:
                    await b.place_order(agent_id="evt", stock_code="600519", side="buy", quantity=100)
                    self._bought = True

        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 3, 4), end_date=date(2024, 3, 15)),
            data_provider=provider, event_bus=bus,
        )
        env.run(Buyer())
        assert "run_start" in events
        assert "run_end" in events
        assert "order_placed" in events


# ============================================================
# Test 6: Tool handlers work with real full-market data
# ============================================================

class TestToolsWithRealData:
    @pytest.mark.asyncio
    async def test_get_kline_real(self, provider):
        df = await provider.get_daily_bars("600519", date(2023, 1, 1), date(2025, 1, 1))
        ctx = ToolContext(
            current_date=date(2024, 6, 1),
            current_phase="pre_market",
            portfolio=Portfolio(initial_cash=Decimal("1000000")),
            initial_cash=Decimal("1000000"),
            preloaded_daily={"600519": df},
        )
        result = await GET_KLINE.handler({"stock_code": "600519", "days": 60}, ctx)
        assert "data" in result
        assert result["count"] == 60
        # Verify date isolation: no dates >= 2024-06-01
        for bar in result["data"]:
            assert bar["date"] < "2024-06-01"

    @pytest.mark.asyncio
    async def test_screen_stocks_real(self, provider):
        stocks = await provider.get_stock_list()
        preloaded = {}
        for s in stocks[:50]:
            df = await provider.get_daily_bars(s["code"], date(2024, 1, 1), date(2024, 12, 31))
            if not df.empty:
                preloaded[s["code"]] = df

        ctx = ToolContext(
            current_date=date(2024, 6, 1),
            current_phase="pre_market",
            portfolio=Portfolio(initial_cash=Decimal("1000000")),
            initial_cash=Decimal("1000000"),
            preloaded_daily=preloaded,
        )
        result = await SCREEN_STOCKS.handler({"max_results": 10}, ctx)
        assert "stocks" in result
        assert len(result["stocks"]) <= 10
        assert result["total_matched"] > 0


# ============================================================
# Test 7: Benchmark comparison with real data
# ============================================================

class TestBenchmarkComparisonReal:
    def test_agent_vs_passive(self, env_2024h1):
        class ActiveAgent:
            agent_id = "active"
            name = "Active"
            _day = 0
            async def on_day(self, bus, d):
                self._day += 1
                if self._day == 5:
                    await bus.place_order(agent_id="active", stock_code="600519", side="buy", quantity=200)
                if self._day == 80:
                    await bus.place_order(agent_id="active", stock_code="600519", side="sell", quantity=200)

        class PassiveAgent:
            agent_id = "passive"
            name = "Passive"
            async def on_day(self, bus, d): pass

        result = env_2024h1.run([ActiveAgent(), PassiveAgent()])

        active_equity = result.agent_data["active"]["equity_curve"]
        passive_equity = result.agent_data["passive"]["equity_curve"]

        comparison = compare_vs_benchmark(active_equity, passive_equity, Decimal("1000000"))
        # Active agent traded, so should differ from passive
        assert comparison.agent_return_pct != comparison.benchmark_return_pct


# ============================================================
# Test 8: 120-day backtest with multiple trades
# ============================================================

class TestLongBacktest:
    def test_120_days_no_crash(self, provider):
        class FrequentTrader:
            agent_id = "freq"
            name = "FreqTrader"
            _day = 0
            _holding = False
            async def on_day(self, bus, d):
                self._day += 1
                if self._day % 20 == 5 and not self._holding:
                    r = await bus.place_order(agent_id="freq", stock_code="000001", side="buy", quantity=1000)
                    if r.get("success"):
                        self._holding = True
                elif self._day % 20 == 15 and self._holding:
                    r = await bus.place_order(agent_id="freq", stock_code="000001", side="sell", quantity=1000)
                    if r.get("success"):
                        self._holding = False

        env = TradingEnv(
            config=EnvConfig(start_date=date(2024, 1, 2), end_date=date(2024, 7, 31), initial_cash=Decimal("1000000")),
            data_provider=provider,
        )
        result = env.run(FrequentTrader())
        trades = result.agent_data["freq"]["trades"]
        equity = result.agent_data["freq"]["equity_curve"]

        assert result.trading_days > 120
        assert len(trades) >= 6  # at least 3 round-trips
        metrics = calculate_metrics(equity, Decimal("1000000"), trades)
        assert metrics.trading_days > 120
        assert metrics.total_trades >= 3
