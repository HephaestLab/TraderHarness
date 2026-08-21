"""Executable audit of every Agent-facing v5 tool contract."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.agents.loop import AgentLoop, PhaseProtocolError, _serialize_tool_result
from traderharness.agents.tool_agent import TOOL_DEFINITIONS
from traderharness.core.portfolio import Portfolio
from traderharness.tools.catalog import ALL_TOOL_NAMES, tool_catalog_payload
from traderharness.tools.contracts import (
    CURRENT_TOOL_CONTRACT_VERSION,
    TOOL_EXAMPLES,
    TOOL_RESULT_SUMMARIES,
    validate_instance,
)
from traderharness.tools.market import handle_get_stock_price
from traderharness.tools.registry import ToolContext, ToolDefinition, ToolRegistry


def _context(**overrides) -> ToolContext:
    values = {
        "current_date": date(2024, 3, 4),
        "current_phase": "pre_market",
        "portfolio": Portfolio(initial_cash=Decimal("1000000")),
        "initial_cash": Decimal("1000000"),
        "tool_contract_version": CURRENT_TOOL_CONTRACT_VERSION,
    }
    values.update(overrides)
    return ToolContext(**values)


def _registry(*, ctx: ToolContext | None = None) -> ToolRegistry:
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    for definition in TOOL_DEFINITIONS:
        registry.register(definition)
    return registry


def _assert_property_descriptions(schema: dict) -> None:
    for name, prop in schema.get("properties", {}).items():
        assert prop.get("description"), f"missing description for {name}"
        if prop.get("type") == "object":
            _assert_property_descriptions(prop)


def test_every_public_tool_has_v5_input_output_example_and_field_docs():
    ctx = _context(require_structured_plan=True, require_decision_card=True)
    contracts = _registry().get_contract_catalog(ctx=ctx)

    assert len(contracts) == 30
    assert {item["name"] for item in contracts} == ALL_TOOL_NAMES
    assert set(TOOL_EXAMPLES) == ALL_TOOL_NAMES
    assert set(TOOL_RESULT_SUMMARIES) == ALL_TOOL_NAMES
    for item in contracts:
        assert item["input"]["type"] == "object"
        assert item["input"]["additionalProperties"] is False
        assert item["output"]["oneOf"]
        assert isinstance(item["example"], dict)
        _assert_property_descriptions(item["input"])


def test_every_published_example_satisfies_its_schema():
    ctx = _context()
    by_name = {item["name"]: item for item in _registry().get_contract_catalog(ctx=ctx)}

    for name, example in TOOL_EXAMPLES.items():
        assert validate_instance(example, by_name[name]["input"]) == [], name


def test_contextual_and_operation_specific_requirements_are_machine_validated():
    strict_ctx = _context(require_structured_plan=True, require_decision_card=True)
    by_name = {item["name"]: item for item in _registry().get_contract_catalog(ctx=strict_ctx)}

    buy_issues = validate_instance(
        {
            "action": "buy",
            "stock_code": "SHM-000360",
            "quantity": 50,
            "reasoning": "尝试建仓",
        },
        by_name["place_order"]["input"],
    )
    buy_messages = {issue["message"] for issue in buy_issues}
    assert "必须是 100 的整数倍" in buy_messages
    assert "缺少必填字段 decision_card" in buy_messages
    assert "缺少必填字段 behavior_hypothesis" in buy_messages

    update_issues = validate_instance(
        {"operation": "update", "order_id": "co-001", "reasoning": "上移止损"},
        by_name["manage_conditional_order"]["input"],
    )
    assert any("anyOf" in issue["message"] for issue in update_issues)

    protective_issues = validate_instance(
        {
            "operation": "create",
            "action": "buy",
            "stock_code": "SHM-000360",
            "quantity": 100,
            "comparator": "price_gte",
            "trigger_price": 30,
            "protective": True,
            "reasoning": "突破买入",
        },
        by_name["manage_conditional_order"]["input"],
    )
    protective_paths = {issue["path"] for issue in protective_issues}
    assert {"$.action", "$.quantity", "$.comparator"} <= protective_paths


def test_catalog_exposes_examples_and_both_result_contracts():
    catalog = tool_catalog_payload()

    assert len(catalog) == 30
    for item in catalog:
        assert isinstance(item["example_arguments"], dict)
        assert item["success_result"]
        assert item["error_contract"]["required"] == [
            "success",
            "error",
            "error_code",
            "retryable",
            "correction",
        ]


@pytest.mark.asyncio
async def test_invalid_arguments_never_reach_handler_and_return_repair_payload():
    calls = []

    async def handler(params, ctx):
        calls.append(params)
        return {"ok": True}

    definition = ToolDefinition(
        name="get_stock_price",
        description="price",
        parameters={
            "type": "object",
            "properties": {"stock_code": {"type": "string"}},
            "required": ["stock_code"],
        },
        handler=handler,
    )
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    registry.register(definition)

    result = await registry.execute(
        "get_stock_price",
        {"stock_code": 600519, "invented": True},
        _context(),
    )

    assert calls == []
    assert result["success"] is False
    assert result["error_code"] == "invalid_tool_arguments"
    assert result["retryable"] is True
    assert result["correction"]["valid_arguments_example"] == {"stock_code": "SHM-000360"}
    assert {issue["path"] for issue in result["correction"]["issues"]} == {
        "$.stock_code",
        "$.invented",
    }


@pytest.mark.asyncio
async def test_handler_errors_are_normalized_for_self_correction():
    async def handler(params, ctx):
        return {"error": "当前交易日之前无该股票K线数据"}

    definition = ToolDefinition(
        name="get_kline",
        description="kline",
        parameters={
            "type": "object",
            "properties": {"stock_code": {"type": "string"}},
            "required": ["stock_code"],
        },
        handler=handler,
    )
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    registry.register(definition)

    result = await registry.execute(
        "get_kline",
        {"stock_code": "SHM-000360"},
        _context(),
    )

    assert result["success"] is False
    assert result["error_code"] == "security_data_unavailable"
    assert result["retryable"] is False
    assert result["correction"]["tool"] == "get_kline"
    assert result["correction"]["received_arguments"] == {"stock_code": "SHM-000360"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "error_code", "retryable", "required_tool"),
    [
        ("未找到板块「火星产业」", "sector_not_found", True, "get_market_overview"),
        ("记忆不存在或不可见", "memory_not_found", True, "search_memory"),
        ("禁止导入: os", "sandbox_disallowed_code", True, None),
        (
            "未知条件单: cond-9999",
            "conditional_order_state_conflict",
            True,
            "list_conditional_orders",
        ),
        ("600519 为ST股，禁止交易", "security_ineligible", False, None),
    ],
)
async def test_common_handler_failures_have_specific_actionable_codes(message, error_code, retryable, required_tool):
    async def handler(params, ctx):
        return {"error": message}

    definition = ToolDefinition(
        name="get_stock_price",
        description="test",
        parameters={
            "type": "object",
            "properties": {"stock_code": {"type": "string"}},
            "required": ["stock_code"],
        },
        handler=handler,
    )
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    registry.register(definition)

    result = await registry.execute(
        "get_stock_price",
        {"stock_code": "SHM-000360"},
        _context(),
    )

    assert result["error_code"] == error_code
    assert result["retryable"] is retryable
    if required_tool is not None:
        assert result["correction"]["required_tool"] == required_tool


def test_large_v5_tool_result_is_still_valid_json_with_truncation_metadata():
    payload = {
        "success": True,
        "rows": [{"stock_code": f"SHM-{index:06d}", "text": "证据" * 500} for index in range(50)],
    }

    encoded = _serialize_tool_result(payload)
    decoded = json.loads(encoded)

    assert len(encoded) <= 3000
    assert decoded["success"] is True
    assert decoded["_truncation"]["truncated"] is True


@pytest.mark.asyncio
async def test_v5_stock_price_distinguishes_premarket_and_visible_window_price():
    daily = pd.DataFrame(
        {
            "date": [date(2024, 3, 1), date(2024, 3, 4)],
            "open": [9.5, 10.5],
            "high": [10.5, 11.5],
            "low": [9.0, 10.0],
            "close": [10.0, 11.0],
            "volume": [1000, 1200],
        }
    )

    class Bus:
        @staticmethod
        def get_execution_price(code, window):
            assert (code, window) == ("600519", "open_1")
            return Decimal("12.00")

    premarket = _context(
        current_date=date(2024, 3, 5),
        preloaded_daily={"600519": daily},
    )
    before_open = await handle_get_stock_price({"stock_code": "600519"}, premarket)

    intraday = _context(
        current_phase="open_window",
        current_date=date(2024, 3, 5),
        preloaded_daily={"600519": daily},
        _bus=Bus(),
    )
    intraday._current_sub_window = "open_1"
    visible = await handle_get_stock_price({"stock_code": "600519"}, intraday)

    assert before_open["price"] == 11.0
    assert before_open["price_source"] == "previous_daily_close"
    assert before_open["tradable_execution_price"] is False
    assert visible == {
        "stock_code": "600519",
        "day": "D+0",
        "price": 12.0,
        "close": 12.0,
        "previous_close": 11.0,
        "change_pct": 9.09,
        "price_source": "current_visible_5min_close",
        "as_of": "open_1",
        "tradable_execution_price": True,
    }


class _StubClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, tools=None, temperature=None):
        self.calls.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_invalid_completion_call_cannot_end_v5_phase():
    def call(call_id, arguments):
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": "complete_phase",
                "arguments": json.dumps(arguments),
            },
        }

    client = _StubClient(
        [
            {
                "content": "",
                "tool_calls": [call("invalid", {"decision": "no_trade"})],
            },
            {
                "content": "",
                "tool_calls": [
                    call(
                        "corrected",
                        {"decision": "no_trade", "summary": "证据不足"},
                    )
                ],
            },
        ]
    )
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    from traderharness.tools.control import COMPLETE_PHASE

    registry.register(COMPLETE_PHASE)
    loop = AgentLoop(client, registry, "system")
    loop._context.add_message({"role": "user", "content": "open"})
    ctx = _context(
        current_phase="open_window",
        require_phase_completion=True,
    )
    ctx._current_sub_window = "open_1"

    await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

    assert len(client.calls) == 2
    assert ctx.tool_call_cache["_completed_phases"]["open_window:open_1"] == {
        "decision": "no_trade",
        "summary": "证据不足",
    }
    first_tool_result = next(
        json.loads(message["content"])
        for message in loop._context._messages
        if message.get("tool_call_id") == "invalid"
    )
    assert first_tool_result["error_code"] == "invalid_tool_arguments"


@pytest.mark.asyncio
async def test_finish_day_fallback_retries_invalid_json_until_tool_succeeds():
    def finish_call(call_id, arguments):
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": "finish_day", "arguments": arguments},
        }

    client = _StubClient(
        [
            {
                "content": "",
                "tool_calls": [finish_call("broken", '{"summary":')],
            },
            {
                "content": "",
                "tool_calls": [finish_call("fixed", json.dumps({"summary": "已完成日终复盘"}))],
            },
        ]
    )
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    from traderharness.tools.control import FINISH_DAY

    registry.register(FINISH_DAY)
    loop = AgentLoop(client, registry, "system")
    ctx = _context(current_phase="close_window")
    ctx._current_sub_window = "close_2"

    summary = await loop._ensure_finish(ctx)

    assert summary == "已完成日终复盘"
    assert len(client.calls) == 2
    assert ctx.tool_call_cache["finish_day_summary"] == summary
    broken_result = next(
        json.loads(message["content"]) for message in loop._context._messages if message.get("tool_call_id") == "broken"
    )
    assert broken_result["error_code"] == "invalid_tool_arguments_json"


@pytest.mark.asyncio
async def test_v5_phase_never_silently_advances_when_completion_budget_is_exhausted():
    client = _StubClient([{"content": "仍在思考"}] * 9)
    registry = ToolRegistry(contract_version=CURRENT_TOOL_CONTRACT_VERSION)
    from traderharness.tools.control import COMPLETE_PHASE

    registry.register(COMPLETE_PHASE)
    loop = AgentLoop(client, registry, "system")
    loop._context.add_message({"role": "user", "content": "open"})
    ctx = _context(
        current_phase="open_window",
        require_phase_completion=True,
    )
    ctx._current_sub_window = "open_1"

    with pytest.raises(PhaseProtocolError, match="未在纠错预算内"):
        await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

    assert ctx.tool_call_cache["_phase_protocol_failure"] == {
        "phase": "open_window",
        "sub_window": "open_1",
        "error_code": "phase_completion_protocol_exhausted",
        "pending_tool_corrections": {},
    }
