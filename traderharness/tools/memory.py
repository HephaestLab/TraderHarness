"""Agent-facing access to deterministic layered memory."""

from __future__ import annotations

from datetime import timedelta

from traderharness.tools.registry import ToolContext, ToolDefinition


def _memory(ctx: ToolContext):
    memory = ctx.tool_call_cache.get("_memory")
    if memory is None:
        raise ValueError("当前 Agent 未配置持久记忆")
    return memory


async def handle_remember(params: dict, ctx: ToolContext) -> dict:
    memory = _memory(ctx)
    record = memory.remember(
        ctx.current_date,
        params.get("content", ""),
        memory_type=params.get("memory_type", "lesson"),
        tags=params.get("tags") or [],
        importance=params.get("importance", 0.5),
        source="agent",
        supersedes_id=params.get("supersedes_id"),
    )
    return {"success": True, "memory": record}


async def handle_search_memory(params: dict, ctx: ToolContext) -> dict:
    memory = _memory(ctx)
    results = memory.search(
        params.get("query", ""),
        before_date=ctx.current_date + timedelta(days=1),
        memory_type=params.get("memory_type"),
        max_results=params.get("max_results", 5),
    )
    return {"count": len(results), "memories": results}


async def handle_get_memory(params: dict, ctx: ToolContext) -> dict:
    record = _memory(ctx).get(
        params.get("memory_id", ""), before_date=ctx.current_date + timedelta(days=1)
    )
    if record is None:
        return {"error": "记忆不存在或在当前时间点尚不可见"}
    return {"memory": record}


REMEMBER = ToolDefinition(
    name="remember",
    description="保存可复用的事实、持仓假设或复盘教训；可用 supersedes_id 留痕替换旧版本。",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "简洁、可验证的记忆内容"},
            "memory_type": {
                "type": "string",
                "enum": ["lesson", "hypothesis", "position_plan", "risk_rule", "observation"],
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "number", "minimum": 0, "maximum": 1},
            "supersedes_id": {"type": "string", "description": "被本记录替代的活动 memory_id"},
        },
        "required": ["content", "memory_type"],
    },
    handler=handle_remember,
)

SEARCH_MEMORY = ToolDefinition(
    name="search_memory",
    description="按关键词检索未自动注入上下文的历史记忆和教训。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "memory_type": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
    handler=handle_search_memory,
)

GET_MEMORY = ToolDefinition(
    name="get_memory",
    description="按 memory_id 读取完整记忆记录及其版本状态。",
    parameters={
        "type": "object",
        "properties": {"memory_id": {"type": "string"}},
        "required": ["memory_id"],
    },
    handler=handle_get_memory,
)
