"""Account-view contracts used by dynamic LLM position sizing."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from traderharness.agents.loop import DayResult
from traderharness.agents.tool_agent import ToolAgent
from traderharness.core.portfolio import Portfolio


class _StubLLM:
    model = "stub"


class _Market:
    def __init__(self, frame):
        self.frame = frame

    def all_codes(self):
        return ["000001"]

    def get(self, code):
        return self.frame


@pytest.mark.asyncio
async def test_tool_context_keeps_run_initial_cash_after_portfolio_changes(tmp_path):
    initial_cash = Decimal("1000000")
    portfolio = Portfolio(initial_cash)
    portfolio.buy("000001", "test", Decimal("10"), 10_000, date(2024, 3, 1))
    frame = pd.DataFrame(
        {
            "date": [date(2024, 3, 1), date(2024, 3, 4)],
            "open": [10.0, 11.0],
            "high": [10.0, 11.0],
            "low": [10.0, 11.0],
            "close": [10.0, 11.0],
            "volume": [1000, 1000],
        }
    )
    bus = SimpleNamespace(
        _portfolio=portfolio,
        market=_Market(frame),
        _news_manager=None,
        _fundamentals_df=None,
        _business_segments_df=None,
        _valuation_df=None,
        _corporate_actions_today=[],
        _total_days=1,
        _day_index=0,
        _entity_masker=None,
    )
    agent = ToolAgent(
        agent_id="account",
        name="account",
        llm_client=_StubLLM(),
        initial_cash=initial_cash,
        memory_dir=str(tmp_path),
        workspace_root=str(tmp_path / "sandbox"),
    )
    agent._loop.run_day = AsyncMock(return_value=DayResult())

    await agent.on_day(bus, date(2024, 3, 5))

    context = agent._loop.run_day.await_args.args[1]
    assert context.initial_cash == initial_cash
    assert context.workspace_root == str(tmp_path / "sandbox")
