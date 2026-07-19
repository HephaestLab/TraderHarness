"""Tool call deduplication — returns cached hint for identical calls within same day."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from traderharness.tools.registry import ToolContext


def with_dedup(
    handler: Callable[[dict, ToolContext], Awaitable[dict]],
) -> Callable[[dict, ToolContext], Awaitable[dict]]:
    """Wrap a tool handler with deduplication.

    If the same handler is called with the same params within the same ToolContext,
    returns a short dedup hint instead of the full result (saves tokens).
    Does not cache error results.
    """

    async def wrapper(params: dict, ctx: ToolContext) -> dict:
        cache_key = f"_dedup_{handler.__name__}_{json.dumps(params, sort_keys=True, default=str)}"

        cached = ctx.tool_call_cache.get(cache_key)
        if cached is not None:
            return {"_dedup": True, "_hint": "(same as previous call, data unchanged)"}

        result = await handler(params, ctx)

        # Only cache successful results
        if "error" not in result:
            ctx.tool_call_cache[cache_key] = True

        return result

    wrapper.__name__ = handler.__name__
    return wrapper
