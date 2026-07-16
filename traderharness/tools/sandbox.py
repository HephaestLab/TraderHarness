"""execute_code tool — Python sandbox with traderharness_api injection.

Replaces read_file/write_file/list_files/run_script with a single powerful tool.
Agent writes arbitrary Python, gets market/portfolio/news via `traderharness_api`.
"""

from __future__ import annotations

import json
import sys
import io
import traceback
from typing import Any

from traderharness.tools.registry import ToolDefinition, ToolContext
from traderharness.agents.sandbox.api import build_api_module


SANDBOX_TIMEOUT = 60


async def handle_execute_code(params: dict, ctx: ToolContext) -> dict:
    code = params.get("code", "")
    if not code.strip():
        return {"error": "code 不能为空"}

    api_module = build_api_module(ctx)

    # Build a module-like namespace for `from traderharness_api import market, portfolio, news`
    import types
    fake_module = types.ModuleType("traderharness_api")
    fake_module.market = api_module["market"]
    fake_module.portfolio = api_module["portfolio"]
    fake_module.news = api_module["news"]

    old_modules = {}
    if "traderharness_api" in sys.modules:
        old_modules["traderharness_api"] = sys.modules["traderharness_api"]
    sys.modules["traderharness_api"] = fake_module

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    result_value: Any = None
    error_msg: str | None = None

    try:
        sys.stdout = stdout_capture
        from traderharness.agents.sandbox.guard import build_sandbox_globals
        exec_globals = build_sandbox_globals(fake_module, ctx.workspace_root)

        import threading

        def _run():
            nonlocal result_value, error_msg
            try:
                exec(compile(code, "<agent_code>", "exec"), exec_globals)
                if "result" in exec_globals:
                    result_value = exec_globals["result"]
            except Exception:
                error_msg = traceback.format_exc()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=SANDBOX_TIMEOUT)

        if thread.is_alive():
            error_msg = f"执行超时（{SANDBOX_TIMEOUT}秒限制）"

    finally:
        sys.stdout = old_stdout
        if old_modules:
            sys.modules["traderharness_api"] = old_modules["traderharness_api"]
        else:
            sys.modules.pop("traderharness_api", None)

    stdout_text = stdout_capture.getvalue()
    if len(stdout_text) > 5000:
        stdout_text = stdout_text[:5000] + "\n... (truncated)"

    response: dict = {}
    if stdout_text:
        response["stdout"] = stdout_text
    if error_msg:
        response["error"] = error_msg
    if result_value is not None:
        try:
            response["result"] = json.loads(json.dumps(result_value, default=str))
        except (TypeError, ValueError):
            response["result"] = str(result_value)[:2000]

    if not response:
        response["stdout"] = "(no output)"

    return response


EXECUTE_CODE = ToolDefinition(
    name="execute_code",
    description=(
        "执行 Python 代码。通过 `from traderharness_api import market, portfolio, news` "
        "访问市场数据（自动遮罩到当前日期之前）。可自由 import numpy/pandas/scipy。"
        "超时60秒。将结果赋值给 `result` 变量可在返回值中看到。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码",
            },
        },
        "required": ["code"],
    },
    handler=handle_execute_code,
)
