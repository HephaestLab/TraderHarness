"""Tests for ToolRegistry."""

from datetime import date
from decimal import Decimal

import pytest

from finharness.tools.registry import ToolDefinition, ToolRegistry, ToolContext
from finharness.core.portfolio import Portfolio


async def _dummy_handler(params: dict, ctx) -> dict:
    return {"result": "ok", **params}


def _make_ctx() -> ToolContext:
    return ToolContext(
        current_date=date(2024, 3, 4),
        current_phase="pre_market",
        portfolio=Portfolio(initial_cash=Decimal("1000000")),
        initial_cash=Decimal("1000000"),
    )


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ToolDefinition(name="test", description="A test", parameters={}, handler=_dummy_handler)
        reg.register(tool)
        assert reg.get_tool("test") is not None
        assert "test" in reg

    def test_get_openai_tools_schema(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="get_kline", description="Get K-line",
                                    parameters={"type": "object", "properties": {}}, handler=_dummy_handler))
        schemas = reg.get_openai_tools_schema()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "get_kline"

    def test_exclude_tools(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", description="", parameters={}, handler=_dummy_handler))
        reg.register(ToolDefinition(name="b", description="", parameters={}, handler=_dummy_handler))
        schemas = reg.get_openai_tools_schema(exclude={"b"})
        names = [s["function"]["name"] for s in schemas]
        assert "a" in names
        assert "b" not in names

    @pytest.mark.asyncio
    async def test_execute(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="echo", description="", parameters={}, handler=_dummy_handler))
        ctx = _make_ctx()
        result = await reg.execute("echo", {"msg": "hi"}, ctx)
        assert result["msg"] == "hi"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        ctx = _make_ctx()
        result = await reg.execute("unknown", {}, ctx)
        assert "error" in result
