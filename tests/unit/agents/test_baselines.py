"""Tests for baseline agents."""

from datetime import date

import pytest

from finharness.agents.baselines.buy_hold import BuyHoldAgent
from finharness.agents.baselines.random_agent import RandomAgent


class FakeEnv:
    def __init__(self):
        self.orders: list[dict] = []

    def place_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"success": True}


class TestBuyHoldAgent:
    @pytest.mark.asyncio
    async def test_buys_on_first_day(self):
        agent = BuyHoldAgent(stock_codes=["600519", "000001"])
        env = FakeEnv()
        await agent.on_day(env, date(2024, 3, 4))
        assert len(env.orders) == 2
        assert env.orders[0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_holds_on_subsequent_days(self):
        agent = BuyHoldAgent(stock_codes=["600519"])
        env = FakeEnv()
        await agent.on_day(env, date(2024, 3, 4))
        await agent.on_day(env, date(2024, 3, 5))
        assert len(env.orders) == 1  # only bought once


class TestRandomAgent:
    @pytest.mark.asyncio
    async def test_trades_with_probability(self):
        agent = RandomAgent(stock_codes=["600519"], trade_probability=1.0, seed=42)
        env = FakeEnv()
        await agent.on_day(env, date(2024, 3, 4))
        assert len(env.orders) == 1

    @pytest.mark.asyncio
    async def test_no_trade_when_zero_probability(self):
        agent = RandomAgent(stock_codes=["600519"], trade_probability=0.0, seed=42)
        env = FakeEnv()
        await agent.on_day(env, date(2024, 3, 4))
        assert len(env.orders) == 0
