"""文件系统工具 — read_file, write_file, list_files。

从源项目 backend/agents/agentic/tools/filesystem_tools.py 迁移。
"""

from __future__ import annotations

from traderharness.tools.registry import ToolDefinition, ToolContext
from traderharness.agents.sandbox.workspace import AgentWorkspace


def _get_workspace(ctx: ToolContext) -> AgentWorkspace:
    if ctx._workspace is None:
        ctx._workspace = AgentWorkspace(ctx.workspace_root or "default")
    return ctx._workspace


async def handle_read_file(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", "")
    if not path:
        return {"error": "path 不能为空"}
    try:
        ws = _get_workspace(ctx)
        content = ws.read(path)
        return {"path": path, "content": content, "size": len(content)}
    except FileNotFoundError:
        return {"error": f"文件不存在: {path}"}
    except ValueError as e:
        return {"error": str(e)}


async def handle_write_file(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", "")
    content = params.get("content", "")
    if not path:
        return {"error": "path 不能为空"}
    try:
        ws = _get_workspace(ctx)
        ws.write(path, content)
        return {"success": True, "path": path, "size": len(content)}
    except ValueError as e:
        return {"error": str(e)}


async def handle_list_files(params: dict, ctx: ToolContext) -> dict:
    ws = _get_workspace(ctx)
    entries = ws.list_files()
    return {"entries": entries, "count": len(entries)}


READ_FILE = ToolDefinition(
    name="read_file", description="读取工作目录中的文件",
    parameters={"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}}, "required": ["path"]},
    handler=handle_read_file,
)

WRITE_FILE = ToolDefinition(
    name="write_file", description="在工作目录中创建或覆盖文件",
    parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    handler=handle_write_file,
)

LIST_FILES = ToolDefinition(
    name="list_files", description="列出工作目录中的文件",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=handle_list_files,
)
