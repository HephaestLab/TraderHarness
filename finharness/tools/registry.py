"""Tool registry — register, discover, and invoke agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable
    phase_restricted: list[str] = field(default_factory=list)

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Manages available tools for agents."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self, phase: str | None = None) -> list[ToolDef]:
        if phase is None:
            return list(self._tools.values())
        return [
            t for t in self._tools.values()
            if not t.phase_restricted or phase in t.phase_restricted
        ]

    def to_openai_schemas(self, phase: str | None = None) -> list[dict]:
        return [t.to_openai_schema() for t in self.list_tools(phase)]

    async def invoke(self, name: str, arguments: dict, context: Any = None) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = tool.handler(context=context, **arguments)
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
