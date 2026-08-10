"""Agent-facing memory tools preserve time and entity boundaries."""

from datetime import date
from decimal import Decimal

import pytest

from traderharness.agents.memory import DailyMemory
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.portfolio import Portfolio
from traderharness.tools.memory import GET_MEMORY, REMEMBER, SEARCH_MEMORY
from traderharness.tools.registry import ToolContext, ToolRegistry


def _context() -> ToolContext:
    ctx = ToolContext(
        current_date=date(2024, 3, 5),
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        agent_id="agent",
    )
    ctx.entity_masker = EntityMasker(
        ["600519", "600000"],
        names={"600519": "贵州茅台", "600000": "浦发银行"},
        seed=1,
    )
    ctx.tool_call_cache["_memory"] = DailyMemory("agent")
    return ctx


@pytest.mark.asyncio
async def test_memory_round_trip_is_masked_to_agent_and_canonical_at_rest():
    ctx = _context()
    registry = ToolRegistry()
    for tool in (REMEMBER, SEARCH_MEMORY, GET_MEMORY):
        registry.register(tool)
    masked_code = ctx.entity_masker.mask_code("600519")

    written = await registry.execute(
        "remember",
        {
            "content": f"{masked_code} breakout needs volume confirmation",
            "memory_type": "lesson",
            "tags": [masked_code, "volume"],
        },
        ctx,
    )
    stored = ctx.tool_call_cache["_memory"].get(written["memory"]["memory_id"])
    searched = await registry.execute(
        "search_memory", {"query": f"{masked_code} volume"}, ctx
    )

    assert "600519" in stored["content"]
    assert "600519" not in searched["memories"][0]["content"]
    assert masked_code in searched["memories"][0]["content"]
