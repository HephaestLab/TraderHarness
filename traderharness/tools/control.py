"""Agent-controlled phase and day completion tools."""

from __future__ import annotations

from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition


async def handle_complete_phase(params: dict, ctx: ToolContext) -> dict:
    """Acknowledge that the Agent, rather than an iteration cap, ended a phase."""
    result = {
        "success": True,
        "status": "phase_complete",
        "phase": ctx.current_phase,
        "sub_window": getattr(ctx, "_current_sub_window", None),
        "decision": params["decision"],
        "summary": params["summary"],
        "next_focus": params.get("next_focus", ""),
    }
    if is_current_contract(getattr(ctx, "tool_contract_version", None)):
        result["abandon_error_codes"] = params.get("abandon_error_codes", [])
    return result


async def handle_finish_day(params: dict, ctx: ToolContext) -> dict:
    result = {
        "status": "day_complete",
        "summary_saved": True,
        "trades_today": len(ctx.trade_results),
    }
    if is_current_contract(getattr(ctx, "tool_contract_version", None)):
        result["summary"] = params.get("summary", "")
        result["abandon_error_codes"] = params.get("abandon_error_codes", [])
    return result


COMPLETE_PHASE = ToolDefinition(
    name="complete_phase",
    description=(
        "主动结束当前盘前或盘中子阶段。只有确认当前阶段的研究、下单及纠错都已完成后调用；"
        "调用成功后市场时钟才推进。最后一个收盘阶段请改用 finish_day。"
    ),
    parameters={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["ready", "trade_complete", "no_trade", "monitor"],
                "description": "当前阶段的显式结论。",
            },
            "summary": {
                "type": "string",
                "description": "简要记录已完成的工作、结论以及关键反证。",
            },
            "next_focus": {
                "type": "string",
                "description": "下一阶段需要验证的价格、板块资金或失效条件。",
            },
        },
        "required": ["decision", "summary"],
    },
    handler=handle_complete_phase,
)


FINISH_DAY = ToolDefinition(
    name="finish_day",
    description="结束今天的交易。必须在所有操作完成后调用。请在 summary 中简要回顾今天的分析和操作。",
    parameters={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "今日总结：市场观察、交易决策及理由、持仓变化",
            },
        },
        "required": ["summary"],
    },
    handler=handle_finish_day,
)
