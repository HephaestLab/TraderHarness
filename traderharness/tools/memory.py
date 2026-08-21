"""Agent-facing access to deterministic layered memory."""

from __future__ import annotations

from datetime import timedelta

from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition


def _memory(ctx: ToolContext):
    memory = ctx.tool_call_cache.get("_memory")
    if memory is None:
        raise ValueError("当前 Agent 未配置持久记忆")
    return memory


async def handle_remember(params: dict, ctx: ToolContext) -> dict:
    memory = _memory(ctx)
    supersedes_id = params.get("supersedes_id")
    daily_limit = max(0, int(getattr(ctx, "max_daily_memories", 0)))
    if daily_limit:
        today = ctx.current_date.isoformat()
        writes_today = sum(
            1
            for event in memory.audit_events()
            if event.get("event") == "remember" and event.get("date") == today and event.get("source") == "agent"
        )
        if writes_today >= daily_limit:
            result = {
                "success": False,
                "error_code": "daily_memory_limit_reached",
                "error": (
                    f"今日已写入 {writes_today} 条持久记忆；上限为 {daily_limit}。"
                    "请把日内细节写入 finish_day，只保留可复用结论。"
                ),
            }
            if is_current_contract(getattr(ctx, "tool_contract_version", None)):
                result.update(
                    {
                        "retryable": False,
                        "correction": {
                            "instruction": ("今日不要再调用 remember；把日内信息压缩进 finish_day。"),
                            "writes_today": writes_today,
                            "daily_limit": daily_limit,
                        },
                    }
                )
            return result

    active = memory.active_records(source="agent")
    active_limit = max(0, int(getattr(ctx, "max_active_memories", 0)))
    if active_limit and len(active) >= active_limit and not supersedes_id:
        result = {
            "success": False,
            "error_code": "active_memory_limit_reached",
            "error": (f"活动记忆已达 {active_limit} 条；请用 supersedes_id 修正旧结论，不要继续堆叠。"),
        }
        if is_current_contract(getattr(ctx, "tool_contract_version", None)):
            candidates = [
                {
                    "memory_id": record.get("memory_id"),
                    "memory_type": record.get("memory_type"),
                    "tags": record.get("tags") or [],
                    "content_preview": str(record.get("content", ""))[:160],
                }
                for record in active[-10:]
            ]
            result.update(
                {
                    "retryable": True,
                    "candidate_memories": candidates,
                    "correction": {
                        "instruction": (
                            "从 candidate_memories 选择被修正的活动结论；不确定时先调用 "
                            "search_memory，再把准确 memory_id 放入 supersedes_id 重试。"
                        ),
                        "required_tool_if_uncertain": "search_memory",
                        "required_argument": "supersedes_id",
                        "candidate_memory_ids": [item["memory_id"] for item in candidates if item["memory_id"]],
                    },
                }
            )
        return result

    memory_type = params.get("memory_type", "lesson")
    tags = {str(tag).strip() for tag in params.get("tags") or [] if str(tag).strip()}
    if not supersedes_id and memory_type in {"hypothesis", "position_plan", "observation"}:
        conflicts = [
            record["memory_id"]
            for record in active
            if record.get("memory_type") == memory_type and tags and tags.intersection(record.get("tags") or [])
        ]
        if conflicts:
            result = {
                "success": False,
                "error_code": "memory_requires_supersedes",
                "error": ("同类型、同标签的活动结论已存在；请读取并通过 supersedes_id 更新。"),
                "candidate_memory_ids": conflicts[:10],
            }
            if is_current_contract(getattr(ctx, "tool_contract_version", None)):
                result.update(
                    {
                        "retryable": True,
                        "correction": {
                            "instruction": (
                                "读取 candidate_memory_ids 中的旧结论，选择要修正的一条，"
                                "保持本次 content/type/tags 并补充 supersedes_id 后重试。"
                            ),
                            "required_tool_if_uncertain": "get_memory",
                            "required_argument": "supersedes_id",
                            "candidate_memory_ids": conflicts[:10],
                            "retry_arguments": {
                                **params,
                                "supersedes_id": conflicts[0],
                            },
                        },
                    }
                )
            return result
    record = memory.remember(
        ctx.current_date,
        params.get("content", ""),
        memory_type=memory_type,
        tags=sorted(tags),
        importance=params.get("importance", 0.5),
        source="agent",
        supersedes_id=supersedes_id,
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
    record = _memory(ctx).get(params.get("memory_id", ""), before_date=ctx.current_date + timedelta(days=1))
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
