"""AgentLoop — reasoning_content propagation and truncated-output handling.

These exercise behavior that only became reachable once LLMClient started
actually populating ``_finish_reason`` (see traderharness/agents/llm_client.py).
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from traderharness.agents.loop import (
    AgentLoop,
    _live_event_text,
    _semantic_premarket_allowed_tools,
    _serialize_tool_result,
)
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

    @pytest.mark.asyncio
    async def test_tool_call_excluded_from_current_stage_is_not_executed(self):
        calls = []
        tool_call = {
            "id": "call_hidden",
            "type": "function",
            "function": {"name": "get_kline", "arguments": "{}"},
        }
        client = StubClient([{"content": "", "tool_calls": [tool_call]}])
        registry = ToolRegistry()

        async def handler(params, ctx):
            calls.append(params)
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
        loop._context.add_message({"role": "user", "content": "brief"})

        await loop._run_phase(_ctx(), max_iter=1, exclude_tools={"get_kline"})

        assert calls == []
        tool_message = next(
            message for message in loop._context._messages if message.get("role") == "tool"
        )
        assert "unavailable" in tool_message["content"]

    @pytest.mark.asyncio
    async def test_retryable_decision_card_error_gets_one_place_order_only_retry(self):
        attempts = []

        async def handler(params, ctx):
            attempts.append(params)
            if len(attempts) == 1:
                return {
                    "success": False,
                    "error": "decision_card contains misplaced fields",
                    "error_code": "decision_card_unknown_fields",
                    "retryable": True,
                    "retry_kind": "decision_card_correction",
                    "correction": {
                        "instruction": "Move confirmation_level to order top level.",
                        "invalid_fields": ["confirmation_level"],
                    },
                }
            return {"success": True}

        from traderharness.tools.registry import ToolDefinition

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )

        def order_call(call_id, corrected):
            return {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "place_order",
                    "arguments": '{"corrected": ' + str(corrected).lower() + "}",
                },
            }

        client = StubClient(
            [
                {"content": "", "tool_calls": [order_call("first", False)]},
                {"content": "", "tool_calls": [order_call("retry", True)]},
            ]
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.tool_call_cache = {}
        ctx.agent_id = "repair-agent"

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        assert attempts == [{"corrected": False}, {"corrected": True}]
        assert len(client.calls) == 2
        assert {
            tool["function"]["name"] for tool in client.calls[1]["tools"]
        } == {"place_order"}
        assert "受控纠错" in client.calls[1]["messages"][-1]["content"]
        assert ctx.tool_call_cache["_decision_card_correction_retries"] == 1

    @pytest.mark.asyncio
    async def test_semantic_decision_card_rejection_does_not_trigger_retry(self):
        attempts = []

        async def handler(params, ctx):
            attempts.append(params)
            return {
                "success": False,
                "error": "candidate_rank=weaker_alternative; 较弱备选不能下单",
                "error_code": "decision_card_semantic_rejection",
                "retryable": False,
                "correction": {
                    "instruction": "保持原语义结论，本阶段不得自动改写为可交易。"
                },
            }

        from traderharness.tools.registry import ToolDefinition

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        tool_call = {
            "id": "semantic-rejection",
            "type": "function",
            "function": {"name": "place_order", "arguments": "{}"},
        }
        client = StubClient([{"content": "", "tool_calls": [tool_call]}])
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.tool_call_cache = {}
        ctx.agent_id = "repair-agent"

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        assert attempts == [{}]
        assert len(client.calls) == 1
        assert "_decision_card_correction_retries" not in ctx.tool_call_cache

    @pytest.mark.asyncio
    async def test_correction_retry_cannot_change_candidate_or_semantic_verdict(self):
        attempts = []

        async def handler(params, ctx):
            attempts.append(params)
            return {
                "success": False,
                "error": "unknown evidence id",
                "error_code": "decision_card_unseen_evidence",
                "retryable": True,
                "retry_kind": "decision_card_correction",
                "correction": {"instruction": "replace the evidence id only"},
            }

        from traderharness.tools.registry import ToolDefinition

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )

        def order_call(call_id, rank):
            arguments = {
                "action": "buy",
                "stock_code": "600519",
                "quantity": 100,
                "decision_card": {
                    "decision": "trade",
                    "mode": "leader_attack",
                    "candidate_rank": rank,
                    "text_evidence_ids": ["news:1"],
                },
            }
            return {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "place_order",
                    "arguments": json.dumps(arguments),
                },
            }

        client = StubClient(
            [
                {
                    "content": "",
                    "tool_calls": [order_call("first", "weaker_alternative")],
                },
                {
                    "content": "",
                    "tool_calls": [order_call("retry", "best_expression")],
                },
            ]
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.tool_call_cache = {}
        ctx.agent_id = "repair-agent"

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        assert len(attempts) == 1
        tool_messages = [
            json.loads(message["content"])
            for message in loop._context._messages
            if message.get("role") == "tool"
        ]
        assert tool_messages[-1]["error_code"] == (
            "decision_card_correction_changed_semantics"
        )
        assert tool_messages[-1]["correction"][
            "changed_decision_card_fields"
        ] == ["candidate_rank"]


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


class TestCooperativeCancellation:
    @pytest.mark.asyncio
    async def test_cancelled_before_iteration_skips_llm_request(self):
        client = StubClient([{"content": "must not be consumed"}])
        loop = AgentLoop(client, ToolRegistry(), "system")
        loop.cancel_check = lambda: True
        loop._context.add_message({"role": "user", "content": "brief"})

        await loop._run_phase(_ctx(), max_iter=1, exclude_tools=set())

        assert client.calls == []

    @pytest.mark.asyncio
    async def test_cancelled_during_llm_request_drops_returned_order(self):
        cancelled = False
        executed = []

        class CancellingClient:
            async def chat(self, messages, tools=None, temperature=None):
                nonlocal cancelled
                cancelled = True
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "late-order",
                            "type": "function",
                            "function": {"name": "place_order", "arguments": "{}"},
                        }
                    ],
                }

        from traderharness.tools.registry import ToolDefinition

        async def handler(params, ctx):
            executed.append(params)
            return {"success": True}

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        loop = AgentLoop(CancellingClient(), registry, "system")
        loop.cancel_check = lambda: cancelled
        loop._context.add_message({"role": "user", "content": "trade"})

        await loop._run_phase(_ctx(), max_iter=1, exclude_tools=set())

        assert executed == []


class TestExplicitPhaseProtocol:
    @staticmethod
    def _call(call_id, name, arguments=None):
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments or {}),
            },
        }

    @pytest.mark.asyncio
    async def test_phase_does_not_advance_until_agent_calls_completion_tool(self):
        from traderharness.tools.control import COMPLETE_PHASE

        client = StubClient(
            [
                {"content": "先观察，不调用工具"},
                {
                    "content": "",
                    "tool_calls": [
                        self._call(
                            "done",
                            "complete_phase",
                            {"decision": "no_trade", "summary": "证据不足"},
                        )
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(COMPLETE_PHASE)
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "open"})
        ctx = _ctx()
        ctx.current_phase = "open_window"
        ctx._current_sub_window = "open_1"
        ctx.require_phase_completion = True
        ctx.tool_call_cache = {}
        ctx.agent_id = "explicit-phase"

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        assert len(client.calls) == 2
        assert (
            ctx.tool_call_cache["_completed_phases"]["open_window:open_1"][
                "decision"
            ]
            == "no_trade"
        )
        assert "市场时钟在此之前不会主动推进" in client.calls[0]["messages"][-1]["content"]

    @pytest.mark.asyncio
    async def test_missing_evidence_tool_stays_available_before_order_retry(self):
        from traderharness.tools.control import COMPLETE_PHASE
        from traderharness.tools.registry import ToolDefinition

        order_attempts = 0

        async def order_handler(params, ctx):
            nonlocal order_attempts
            order_attempts += 1
            if order_attempts == 1:
                return {
                    "success": False,
                    "error": "missing valuation",
                    "error_code": "decision_card_missing_tool_evidence",
                    "retryable": True,
                    "retry_kind": "decision_card_correction",
                    "correction": {
                        "instruction": "query valuation then retry",
                        "missing_tools": ["get_valuation"],
                    },
                }
            return {"success": True}

        async def valuation_handler(params, ctx):
            return {"stock_code": "600519", "pe_ttm": 20.0}

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={"type": "object", "properties": {}},
                handler=order_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="get_valuation",
                description="valuation",
                parameters={"type": "object", "properties": {}},
                handler=valuation_handler,
            )
        )
        registry.register(COMPLETE_PHASE)
        client = StubClient(
            [
                {"content": "", "tool_calls": [self._call("order-1", "place_order")]},
                {"content": "", "tool_calls": [self._call("valuation", "get_valuation")]},
                {"content": "", "tool_calls": [self._call("order-2", "place_order")]},
                {
                    "content": "",
                    "tool_calls": [
                        self._call(
                            "done",
                            "complete_phase",
                            {"decision": "trade_complete", "summary": "已成交"},
                        )
                    ],
                },
            ]
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.current_phase = "open_window"
        ctx._current_sub_window = "open_1"
        ctx.require_phase_completion = True
        ctx.tool_call_cache = {}
        ctx.agent_id = "repair-agent"

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        second_surface = {
            tool["function"]["name"] for tool in client.calls[1]["tools"]
        }
        third_surface = {
            tool["function"]["name"] for tool in client.calls[2]["tools"]
        }
        assert {"get_valuation", "place_order", "complete_phase"} <= second_surface
        assert "get_valuation" not in third_surface
        assert {"place_order", "complete_phase"} <= third_surface
        assert order_attempts == 2
        assert len(client.calls) == 4


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

    @pytest.mark.asyncio
    async def test_card_can_limit_sandbox_to_premarket_and_mark_research_days(self):
        from decimal import Decimal

        from traderharness.core.portfolio import Portfolio
        from traderharness.tools.registry import ToolContext, ToolDefinition

        async def handler(params, ctx):
            return {"ok": True}

        registry = ToolRegistry()
        for name in ("execute_code", "finish_day"):
            registry.register(
                ToolDefinition(
                    name=name,
                    description=name,
                    parameters={"type": "object", "properties": {}},
                    handler=handler,
                )
            )
        client = StubClient([{"content": "ok"}] * 6)
        loop = AgentLoop(
            client,
            registry,
            "system",
            max_pre_iterations=1,
            max_window_iterations=1,
        )
        loop.total_trading_days = 1
        loop.remaining_trading_days = 0
        ctx = ToolContext(
            current_date=date(2024, 3, 4),
            current_phase="pre_market",
            portfolio=Portfolio(Decimal("1000000")),
            initial_cash=Decimal("1000000"),
            research_interval_days=5,
            sandbox_pre_market_only=True,
        )

        await loop.run_day(ctx.current_date, ctx)

        first_request_text = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
        assert "剩余" not in first_request_text
        assert "1/1" not in first_request_text
        assert "研究日" in first_request_text

        premarket_names = {tool["function"]["name"] for tool in client.calls[0]["tools"]}
        assert "execute_code" in premarket_names
        assert "finish_day" not in premarket_names
        for call in client.calls[1:5]:
            window_names = {tool["function"]["name"] for tool in call["tools"]}
            assert "execute_code" not in window_names
        for call in client.calls[1:4]:
            assert "finish_day" not in {
                tool["function"]["name"] for tool in call["tools"]
            }
        assert "finish_day" in {
            tool["function"]["name"] for tool in client.calls[4]["tools"]
        }
        assert ctx.full_market_research_allowed is True


def test_semantic_turn_names_only_the_tools_exposed_in_that_request():
    ctx = _ctx()
    ctx.full_market_research_allowed = True
    allowed = _semantic_premarket_allowed_tools(ctx, 0)

    from traderharness.agents.loop import _available_tools_instruction

    instruction = _available_tools_instruction(allowed)

    assert "get_narrative_news" in instruction
    assert "get_kline" not in instruction


class TestSerializeToolResult:
    def test_nan_and_inf_become_null(self):
        text = _serialize_tool_result(
            {"revenue": float("nan"), "eps": float("inf"), "ok": 1.5}
        )
        assert text == '{"revenue": null, "eps": null, "ok": 1.5}'


def test_live_event_text_is_bounded_without_changing_full_trajectory_payload():
    text, truncated = _live_event_text("x" * 5000)

    assert truncated is True
    assert len(text) == 4001
    assert text.endswith("…")


def test_semantic_premarket_stages_constrain_research_workflow_not_verdict():
    ctx = _ctx()
    ctx.full_market_research_allowed = True

    stages = [_semantic_premarket_allowed_tools(ctx, index) for index in range(5)]

    assert "get_narrative_news" in stages[0]
    assert "get_narrative_sector_summary" in stages[1]
    assert stages[2] & {"execute_code"}
    assert "get_business_segments" in stages[3]
    assert "get_valuation" in stages[3]
    assert "get_announcement_evidence" in stages[3]
    assert "get_kline" not in stages[3]
    assert "get_stock_price" not in stages[3]
    assert "add_watchlist" in stages[4]
    assert "execute_code" not in stages[3]
    assert "place_order" not in set().union(*stages)


@pytest.mark.asyncio
async def test_semantic_stage_retries_after_an_unavailable_tool_call():
    from traderharness.tools.registry import ToolDefinition

    executed = []

    async def handler(params, ctx):
        executed.append(params["name"])
        return {"ok": True}

    registry = ToolRegistry()
    for name in (
        "get_kline",
        "get_narrative_news",
        "get_narrative_market_overview",
        "get_narrative_sector_summary",
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string", "default": name}},
                },
                handler=handler,
            )
        )

    def call(call_id, name):
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": '{"name": "' + name + '"}',
            },
        }

    client = StubClient(
        [
            {
                "content": "",
                "tool_calls": [
                    call("bad-1", "get_kline"),
                    call("bad-2", "get_kline"),
                    call("bad-3", "get_kline"),
                    call("bad-4", "get_kline"),
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    call("news", "get_narrative_news"),
                    call("market", "get_narrative_market_overview"),
                ],
            },
            {
                "content": "",
                "tool_calls": [call("sector", "get_narrative_sector_summary")],
            },
        ]
    )
    loop = AgentLoop(client, registry, "system")
    loop._context.add_message({"role": "user", "content": "brief"})
    ctx = _ctx()
    ctx.require_decision_card = True
    ctx.full_market_research_allowed = True

    await loop._run_phase(ctx, max_iter=3, exclude_tools=set())

    schemas = [
        {tool["function"]["name"] for tool in request["tools"]}
        for request in client.calls
    ]
    assert "get_narrative_news" in schemas[0]
    assert "get_narrative_news" in schemas[1]
    assert "get_narrative_sector_summary" in schemas[2]
    assert executed == [
        "get_narrative_news",
        "get_narrative_market_overview",
        "get_narrative_sector_summary",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("second_attempt_succeeds", [True, False])
async def test_semantic_stage_allows_one_traceback_driven_sandbox_correction(
    second_attempt_succeeds,
):
    from traderharness.tools.registry import ToolDefinition

    registry = ToolRegistry()

    async def ok_handler(params, ctx):
        return {"ok": True}

    sandbox_attempts = 0

    async def correcting_sandbox_handler(params, ctx):
        nonlocal sandbox_attempts
        sandbox_attempts += 1
        ctx.tool_call_cache["_sandbox_call_count"] = sandbox_attempts
        if sandbox_attempts == 1:
            ctx.tool_call_cache["_sandbox_last_error"] = True
            return {"stdout": "partial table", "error": "KeyError: chg_5d"}
        ctx.tool_call_cache["_sandbox_last_error"] = not second_attempt_succeeds
        if second_attempt_succeeds:
            return {"stdout": "corrected evidence table"}
        return {"error": "KeyError: still_broken"}

    for name in (
        "get_narrative_news",
        "get_narrative_market_overview",
        "get_narrative_sector_summary",
        "get_stock_info",
        "get_business_segments",
        "get_valuation",
        "add_watchlist",
        "get_kline",
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                handler=ok_handler,
            )
        )
    registry.register(
        ToolDefinition(
            name="execute_code",
            description="execute",
            parameters={"type": "object", "properties": {}},
            handler=correcting_sandbox_handler,
        )
    )

    def call(call_id, name):
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": "{}"},
        }

    client = StubClient(
        [
            {
                "content": "",
                "tool_calls": [
                    call("news", "get_narrative_news"),
                    call("market", "get_narrative_market_overview"),
                ],
            },
            {
                "content": "",
                "tool_calls": [call("sector", "get_narrative_sector_summary")],
            },
            {"content": "", "tool_calls": [call("code-1", "execute_code")]},
            {"content": "", "tool_calls": [call("code-2", "execute_code")]},
            {"content": "", "tool_calls": [call("stock", "get_stock_info")]},
            {
                "content": "",
                "tool_calls": [
                    call("business", "get_business_segments"),
                    call("valuation", "get_valuation"),
                ],
            },
            {"content": "", "tool_calls": [call("review", "get_kline")]},
            {"content": "", "tool_calls": [call("watch", "add_watchlist")]},
        ]
    )
    loop = AgentLoop(client, registry, "system")
    loop._context.add_message({"role": "user", "content": "brief"})
    ctx = _ctx()
    ctx.require_decision_card = True
    ctx.full_market_research_allowed = True
    ctx.sandbox_max_calls_per_day = 2
    ctx.tool_call_cache = {}

    await loop._run_phase(ctx, max_iter=8, exclude_tools=set())

    fourth_schema = {
        tool["function"]["name"] for tool in client.calls[3]["tools"]
    }
    fifth_schema = {
        tool["function"]["name"] for tool in client.calls[4]["tools"]
    }
    assert "execute_code" in fourth_schema
    assert "get_stock_info" not in fourth_schema
    assert "get_stock_info" in fifth_schema
    sixth_schema = {
        tool["function"]["name"] for tool in client.calls[5]["tools"]
    }
    seventh_schema = {
        tool["function"]["name"] for tool in client.calls[6]["tools"]
    }
    eighth_schema = {
        tool["function"]["name"] for tool in client.calls[7]["tools"]
    }
    assert "get_stock_info" not in sixth_schema
    assert {"get_business_segments", "get_valuation"} <= sixth_schema
    assert "Still missing required tools" in client.calls[5]["messages"][-1]["content"]
    assert "add_watchlist" in seventh_schema
    assert "get_kline" in seventh_schema
    assert "get_kline" not in eighth_schema
    assert "add_watchlist" in eighth_schema
    assert sandbox_attempts == 2
    correction_prompt = client.calls[3]["messages"][-1]["content"]
    assert "controlled code correction" in correction_prompt
    assert "one final execute_code attempt" in correction_prompt
    sandbox_message = next(
        message
        for message in loop._context._messages
        if message.get("role") == "tool" and message.get("tool_call_id") == "code-1"
    )
    assert "KeyError: chg_5d" in sandbox_message["content"]


@pytest.mark.asyncio
async def test_nonresearch_day_skips_duplicate_candidate_deep_dive():
    from traderharness.tools.registry import ToolDefinition

    registry = ToolRegistry()

    async def handler(params, ctx):
        return {"ok": True}

    for name in (
        "get_narrative_news",
        "get_narrative_market_overview",
        "get_narrative_sector_summary",
        "get_stock_info",
        "add_watchlist",
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                handler=handler,
            )
        )

    def call(call_id, name):
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": "{}"},
        }

    client = StubClient(
        [
            {
                "content": "",
                "tool_calls": [
                    call("news", "get_narrative_news"),
                    call("market", "get_narrative_market_overview"),
                ],
            },
            {
                "content": "",
                "tool_calls": [call("sector", "get_narrative_sector_summary")],
            },
            {"content": "", "tool_calls": [call("stock", "get_stock_info")]},
            {"content": "", "tool_calls": [call("watch", "add_watchlist")]},
        ]
    )
    loop = AgentLoop(client, registry, "system")
    loop._context.add_message({"role": "user", "content": "brief"})
    ctx = _ctx()
    ctx.require_decision_card = True
    ctx.full_market_research_allowed = False

    await loop._run_phase(ctx, max_iter=7, exclude_tools=set())

    assert len(client.calls) == 4
    assert "get_stock_info" in {
        tool["function"]["name"] for tool in client.calls[2]["tools"]
    }
    assert "add_watchlist" in {
        tool["function"]["name"] for tool in client.calls[3]["tools"]
    }
    assert "Monitoring step 3/4" in client.calls[2]["messages"][-1]["content"]


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
    async def test_replay_keeps_decision_card_schema_for_agent_that_requires_it(self):
        from traderharness.tools.registry import ToolDefinition

        client = _PlayerClient({"content": "done"})
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={
                    "type": "object",
                    "properties": {"decision_card": {"type": "object"}},
                },
                handler=lambda params, ctx: None,
            )
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.current_phase = "open_window"
        ctx.require_decision_card = True

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        place_order = next(
            tool
            for tool in client.calls[0]["tools"]
            if tool["function"]["name"] == "place_order"
        )
        assert "decision_card" in place_order["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_legacy_replay_still_removes_optional_decision_card_schema(self):
        from traderharness.tools.registry import ToolDefinition

        client = _PlayerClient({"content": "done"})
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="place_order",
                description="order",
                parameters={
                    "type": "object",
                    "properties": {"decision_card": {"type": "object"}},
                },
                handler=lambda params, ctx: None,
            )
        )
        loop = AgentLoop(client, registry, "system")
        loop._context.add_message({"role": "user", "content": "trade"})
        ctx = _ctx()
        ctx.current_phase = "open_window"
        ctx.require_decision_card = False

        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

        place_order = next(
            tool
            for tool in client.calls[0]["tools"]
            if tool["function"]["name"] == "place_order"
        )
        assert "decision_card" not in place_order["function"]["parameters"]["properties"]

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
