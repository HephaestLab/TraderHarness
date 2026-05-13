"""脚本执行工具 — run_script with data injection。

从源项目 backend/agents/agentic/tools/filesystem_tools.py 迁移 run_script 部分。
"""

from __future__ import annotations

import json

import pandas as pd

from finharness.tools.registry import ToolDefinition, ToolContext
from finharness.agents.sandbox.executor import PythonSandbox
from finharness.agents.sandbox.workspace import AgentWorkspace


def _get_workspace(ctx: ToolContext) -> AgentWorkspace:
    if ctx._workspace is None:
        ctx._workspace = AgentWorkspace(ctx.workspace_root or "default")
    return ctx._workspace


async def handle_run_script(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", "")
    inject_data_spec = params.get("inject_data", {})

    if not path:
        return {"error": "path 不能为空"}

    ws = _get_workspace(ctx)
    try:
        code = ws.read(path)
    except FileNotFoundError:
        return {"error": f"脚本不存在: {path}"}

    injected = {}
    for var_name, stock_code in (inject_data_spec or {}).items():
        df = ctx.preloaded_daily.get(stock_code)
        if df is not None and not df.empty:
            filtered = df[df["date"] <= ctx.current_date].copy()
            injected[var_name] = filtered
        else:
            injected[var_name] = pd.DataFrame()

    sandbox = PythonSandbox(workspace_root=ws.root)
    result = sandbox.execute(code, injected_data=injected)

    response: dict = {"path": path}
    if result.error:
        response["error"] = result.error
    if result.stdout:
        response["stdout"] = result.stdout
    if result.result is not None:
        try:
            response["result"] = json.loads(json.dumps(result.result, default=str))
        except (TypeError, ValueError):
            response["result"] = str(result.result)

    return response


RUN_SCRIPT = ToolDefinition(
    name="run_script",
    description="执行工作目录中的 Python 脚本。可以注入行情数据作为 DataFrame 变量。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "脚本路径"},
            "inject_data": {
                "type": "object",
                "description": "数据注入: {变量名: 股票代码}",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["path"],
    },
    handler=handle_run_script,
)
