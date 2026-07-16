"""控制工具 — finish_day 结束当天循环。"""

from __future__ import annotations

from traderharness.tools.registry import ToolDefinition, ToolContext


async def handle_finish_day(params: dict, ctx: ToolContext) -> dict:
    return {
        "status": "day_complete",
        "summary_saved": True,
        "trades_today": len(ctx.trade_results),
    }


FINISH_DAY = ToolDefinition(
    name="finish_day",
    description="结束今天的交易。必须在所有操作完成后调用。请在 summary 中简要回顾今天的分析和操作。",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "今日总结：市场观察、交易决策及理由、持仓变化"},
        },
        "required": ["summary"],
    },
    handler=handle_finish_day,
)
