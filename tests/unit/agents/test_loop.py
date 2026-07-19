"""AgentLoop — reasoning_content propagation and truncated-output handling.

These exercise behavior that only became reachable once LLMClient started
actually populating ``_finish_reason`` (see traderharness/agents/llm_client.py).
"""

from datetime import date
from types import SimpleNamespace

import pytest

from traderharness.agents.loop import AgentLoop, _serialize_tool_result
from traderharness.tools.registry import ToolRegistry


class StubClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def chat(self, messages, tools=None, temperature=None):
        self.calls.append({"messages": messages, "tools": tools})
        return self._responses.pop(0)


def _ctx():
    return SimpleNamespace(
        current_date=date(2024, 3, 4),
        current_phase="pre_market",
        _current_sub_window=None,
        date_masker=None,
        entity_masker=None,
    )


class TestReasoningContentWithToolCalls:
    @pytest.mark.asyncio
    async def test_reasoning_content_is_added_to_context_alongside_tool_calls(self):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_kline", "arguments": "{}"},
        }
        client = StubClient(
            [
                {
                    "content": "",
                    "reasoning_content": "先看K线再决定",
                    "tool_calls": [tool_call],
                },
                {"content": "done"},
            ]
        )
        registry = ToolRegistry()

        async def handler(params, ctx):
            return {"ok": True}

        from traderharness.tools.registry import ToolDefinition

        registry.register(
            ToolDefinition(
                name="get_kline",
                description="d",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "晨报"})

        await loop._run_phase(_ctx(), max_iter=2, exclude_tools=set())

        messages = loop._context.get_api_messages()
        assistant_msg = next(m for m in messages if m.get("role") == "assistant" and m.get("tool_calls"))
        assert assistant_msg["reasoning_content"] == "先看K线再决定"
        assert assistant_msg["tool_calls"][0]["function"]["name"] == "get_kline"


class TestTruncatedOutputHandling:
    @pytest.mark.asyncio
    async def test_length_finish_reason_with_empty_content_does_not_crash(self, caplog):
        client = StubClient(
            [{"content": "", "_finish_reason": "length"}],
        )
        registry = ToolRegistry()
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "晨报"})

        await loop._run_phase(_ctx(), max_iter=1, exclude_tools=set())

        assert len(client.calls) == 1
        assert "Output truncated" in caplog.text


class TestPhaseChangeEvents:
    @pytest.mark.asyncio
    async def test_phase_change_events_carry_agent_id(self):
        """Live UIs attribute events per agent; phase_change must say whose
        phase changed, like tool_call/llm_response already do."""
        from decimal import Decimal

        from traderharness.core.events import EventBus
        from traderharness.core.portfolio import Portfolio
        from traderharness.tools.registry import ToolContext

        client = StubClient([{"content": "ok"}] * 5)
        bus = EventBus()
        phase_events = []
        bus.on("phase_change", lambda **kw: phase_events.append(kw))
        loop = AgentLoop(client, ToolRegistry(), "system", event_bus=bus)
        ctx = ToolContext(
            current_date=date(2024, 3, 4),
            current_phase="pre_market",
            portfolio=Portfolio(Decimal("1000000")),
            initial_cash=Decimal("1000000"),
            agent_id="event-hawk",
        )

        await loop.run_day(date(2024, 3, 4), ctx)

        assert [e["phase"] for e in phase_events] == [
            "pre_market",
            "open_window",
            "close_window",
        ]
        assert all(e["agent_id"] == "event-hawk" for e in phase_events)


class TestSerializeToolResult:
    def test_nan_and_inf_become_null(self):
        text = _serialize_tool_result(
            {"revenue": float("nan"), "eps": float("inf"), "ok": 1.5}
        )
        assert text == '{"revenue": null, "eps": null, "ok": 1.5}'


class _MarkingEntityMasker:
    """Appends a marker so double-sanitization is observable."""

    def sanitize_agent_text(self, value):
        return f"{value}|S" if isinstance(value, str) else value

    def sanitize_agent_obj(self, value):
        if isinstance(value, dict):
            return {k: self.sanitize_agent_obj(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.sanitize_agent_obj(v) for v in value]
        if isinstance(value, str):
            return f"{value}|S"
        return value


class _PlayerClient:
    """Minimal replay client: exposes `_player` and returns a fixed response."""

    def __init__(self, response):
        self._player = object()
        self._response = response
        self.calls = []

    async def chat(self, messages, tools=None, temperature=None):
        self.calls.append({"messages": messages, "tools": tools})
        return dict(self._response)


class TestReplaySkipsResponseSanitization:
    @pytest.mark.asyncio
    async def test_replay_does_not_re_sanitize_cassette_output(self):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "get_kline",
                "arguments": '{"stock_code": "公司-AB12CD"}',
            },
        }
        client = _PlayerClient(
            {
                "content": "already-clean",
                "reasoning_content": "think",
                "tool_calls": [tool_call],
            }
        )
        registry = ToolRegistry()
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "晨报"})
        ctx = _ctx()
        ctx.entity_masker = _MarkingEntityMasker()

        # Exclude the tool so the phase stops after one assistant turn without
        # requiring a real tool handler; we only assert sanitize-skip behavior.
        await loop._run_phase(ctx, max_iter=1, exclude_tools={"get_kline"})

        assistant = next(
            m for m in loop._context._messages if m.get("role") == "assistant"
        )
        assert assistant["content"] == "already-clean"
        assert assistant["reasoning_content"] == "think"
        assert assistant["tool_calls"][0]["function"]["arguments"] == (
            '{"stock_code": "公司-AB12CD"}'
        )

    @pytest.mark.asyncio
    async def test_live_still_sanitizes_model_output(self):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "get_kline",
                "arguments": '{"stock_code": "600519"}',
            },
        }
        client = StubClient(
            [
                {
                    "content": "raw",
                    "reasoning_content": "think",
                    "tool_calls": [tool_call],
                },
                {"content": "done"},
            ]
        )
        registry = ToolRegistry()
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "晨报"})
        ctx = _ctx()
        ctx.entity_masker = _MarkingEntityMasker()

        await loop._run_phase(ctx, max_iter=1, exclude_tools={"get_kline"})

        assistant = next(
            m for m in loop._context._messages if m.get("role") == "assistant"
        )
        assert assistant["content"] == "raw|S"
        assert assistant["reasoning_content"] == "think|S"
        assert "|S" in assistant["tool_calls"][0]["function"]["arguments"]
