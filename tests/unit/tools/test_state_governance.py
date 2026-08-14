from datetime import date
from decimal import Decimal

import pytest

from traderharness.agents.memory import DailyMemory
from traderharness.core.portfolio import Portfolio
from traderharness.tools.memory import handle_remember
from traderharness.tools.registry import ToolContext
from traderharness.tools.watchlist import handle_add_watchlist, handle_get_watchlist


def _ctx(**overrides) -> ToolContext:
    values = {
        "current_date": date(2026, 3, 2),
        "current_phase": "pre_market",
        "portfolio": Portfolio(Decimal("1000000")),
        "initial_cash": Decimal("1000000"),
        "day_index": 4,
    }
    values.update(overrides)
    return ToolContext(**values)


@pytest.mark.asyncio
async def test_watchlist_refresh_has_auditable_trading_day_expiry():
    ctx = _ctx(watchlist_ttl_days=10)

    added = await handle_add_watchlist(
        {"stock_code": "600519", "reason": "等待主题分歧转强"}, ctx
    )
    listed = await handle_get_watchlist({}, ctx)

    assert added["expires_in_trading_days"] == 10
    assert listed["watchlist"][0]["expires_in_trading_days"] == 10
    assert ctx.tool_call_cache["_watchlist_meta"]["600519"]["expires_day_index"] == 14


@pytest.mark.asyncio
async def test_memory_requires_replacement_for_same_tagged_hypothesis():
    ctx = _ctx(max_active_memories=24, max_daily_memories=3)
    ctx.tool_call_cache["_memory"] = DailyMemory("governed")
    first = await handle_remember(
        {
            "content": "算力电力主题处于启动期",
            "memory_type": "hypothesis",
            "tags": ["算力电力"],
        },
        ctx,
    )
    duplicate = await handle_remember(
        {
            "content": "算力电力主题进入扩散期",
            "memory_type": "hypothesis",
            "tags": ["算力电力"],
        },
        ctx,
    )

    assert first["success"] is True
    assert duplicate["error_code"] == "memory_requires_supersedes"
    assert duplicate["candidate_memory_ids"] == [first["memory"]["memory_id"]]


@pytest.mark.asyncio
async def test_memory_daily_limit_stops_journal_spam():
    ctx = _ctx(max_daily_memories=1)
    ctx.tool_call_cache["_memory"] = DailyMemory("daily-limit")
    assert (
        await handle_remember(
            {"content": "可复用教训一", "memory_type": "lesson"}, ctx
        )
    )["success"] is True

    rejected = await handle_remember(
        {"content": "可复用教训二", "memory_type": "lesson"}, ctx
    )

    assert rejected["error_code"] == "daily_memory_limit_reached"
