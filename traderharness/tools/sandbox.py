"""execute_code tool — the single Python sandbox entry point.

Agent writes arbitrary Python and accesses data exclusively through
``traderharness_api`` (masked to before current_date). Files in the agent
workspace can be read/written directly with ``open()`` — no separate
read_file/write_file/list_files tools.

Security layers:
- Static AST check + sys.meta_path hook block backtest frameworks
  (no backtest-in-backtest).
- ``build_sandbox_globals`` (guard.py) blocks OS/network escape modules and
  restricts open()/pandas/numpy readers to the workspace.
- Hard 60s timeout.
"""

from __future__ import annotations

import ast
import io
import json
import os
import sys
import threading
import traceback
import types
from pathlib import Path
from typing import Any

from traderharness.agents.sandbox.api import build_api_module
from traderharness.agents.sandbox.guard import build_sandbox_globals
from traderharness.tools.registry import ToolContext, ToolDefinition

SANDBOX_TIMEOUT = 60

BLOCKED_IMPORTS = {
    "traderharness",
    "backtrader",
    "vnpy",
    "zipline",
    "qlib",
    "pyalgotrade",
    "bt",
    "finrl",
}


def _check_blocked_imports(code: str) -> str | None:
    """Static check for blocked imports before execution."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # let runtime surface syntax errors
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_IMPORTS:
                    return (
                        f"禁止导入 '{alias.name}'。沙箱内不能使用回测框架，"
                        "请通过 traderharness_api 访问数据。"
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_IMPORTS:
                return (
                    f"禁止导入 '{node.module}'。沙箱内不能使用回测框架，"
                    "请通过 traderharness_api 访问数据。"
                )
    return None


class _BlockingLoader:
    """Loader that always refuses to create the blocked module."""

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError(f"Module '{module.__spec__.name}' is blocked in sandbox")


class _ImportBlocker:
    """sys.meta_path hook that blocks dangerous imports at runtime."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED_IMPORTS:
            import importlib.util

            return importlib.util.spec_from_loader(fullname, _BlockingLoader())
        return None

    # Legacy finder protocol, still consulted on Python < 3.12.
    def find_module(self, fullname, path=None):
        if fullname.split(".")[0] in BLOCKED_IMPORTS:
            return self
        return None

    def load_module(self, fullname):
        raise ImportError(f"Module '{fullname}' is blocked in sandbox")


async def handle_execute_code(params: dict, ctx: ToolContext) -> dict:
    code = params.get("code", "")
    if not code.strip():
        return {"error": "code 不能为空"}

    block_error = _check_blocked_imports(code)
    if block_error:
        return {"error": block_error}

    api_module = build_api_module(ctx)
    fake_module = types.ModuleType("traderharness_api")
    fake_module.market = api_module["market"]
    fake_module.portfolio = api_module["portfolio"]
    fake_module.news = api_module["news"]

    old_modules = {}
    if "traderharness_api" in sys.modules:
        old_modules["traderharness_api"] = sys.modules["traderharness_api"]
    sys.modules["traderharness_api"] = fake_module

    blocker = _ImportBlocker()
    sys.meta_path.insert(0, blocker)

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    old_cwd = os.getcwd()
    result_value: Any = None
    error_msg: str | None = None

    try:
        # Run inside the workspace so relative open() works.
        workspace = Path(ctx.workspace_root)
        workspace.mkdir(parents=True, exist_ok=True)
        os.chdir(workspace)

        sys.stdout = stdout_capture

        exec_globals = build_sandbox_globals(fake_module, ctx.workspace_root)

        def _run():
            nonlocal result_value, error_msg
            try:
                exec(compile(code, "<agent_code>", "exec"), exec_globals)
                if "result" in exec_globals:
                    result_value = exec_globals["result"]
            except ImportError as e:
                if any(blocked in str(e) for blocked in BLOCKED_IMPORTS):
                    error_msg = f"禁止导入: {e}。沙箱内不能使用回测框架。"
                else:
                    error_msg = traceback.format_exc()
            except Exception:
                error_msg = traceback.format_exc()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=SANDBOX_TIMEOUT)

        if thread.is_alive():
            error_msg = f"执行超时（{SANDBOX_TIMEOUT}秒限制）"

    finally:
        sys.stdout = old_stdout
        os.chdir(old_cwd)
        sys.meta_path.remove(blocker)
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
        "工作目录内的文件可直接 open() 读写（保存笔记/策略/中间结果）。"
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
