"""Tests for ToolRegistry."""

import pytest

from finharness.tools.registry import ToolDef, ToolRegistry


def _dummy_handler(context=None, **kwargs):
    return {"result": "ok", **kwargs}


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ToolDef(name="test", description="A test tool", parameters={}, handler=_dummy_handler)
        reg.register(tool)
        assert reg.get("test") is not None
        assert "test" in reg

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(ToolDef(name="a", description="", parameters={}, handler=_dummy_handler))
        reg.register(ToolDef(name="b", description="", parameters={}, handler=_dummy_handler))
        assert len(reg.list_tools()) == 2

    def test_phase_filtering(self):
        reg = ToolRegistry()
        reg.register(ToolDef(name="unrestricted", description="", parameters={}, handler=_dummy_handler))
        reg.register(ToolDef(
            name="trading_only", description="", parameters={},
            handler=_dummy_handler, phase_restricted=["open_window"],
        ))
        all_tools = reg.list_tools(phase="pre_market")
        names = [t.name for t in all_tools]
        assert "unrestricted" in names
        assert "trading_only" not in names

    def test_to_openai_schemas(self):
        reg = ToolRegistry()
        reg.register(ToolDef(
            name="get_kline", description="Get K-line",
            parameters={"type": "object", "properties": {}},
            handler=_dummy_handler,
        ))
        schemas = reg.to_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "get_kline"

    @pytest.mark.asyncio
    async def test_invoke(self):
        reg = ToolRegistry()
        reg.register(ToolDef(name="echo", description="", parameters={}, handler=_dummy_handler))
        result = await reg.invoke("echo", {"msg": "hi"})
        assert result["msg"] == "hi"

    @pytest.mark.asyncio
    async def test_invoke_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.invoke("unknown", {})
        assert "error" in result
