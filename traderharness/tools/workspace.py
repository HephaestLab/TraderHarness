"""Workspace tools — Agent's file system + Python sandbox.

Gives the Agent a persistent workspace directory with:
- read_file / write_file / list_files — file operations within workspace
- run_python — execute Python with traderharness_api, blocked dangerous imports

Security:
- All file paths resolved relative to workspace root, escape rejected
- Import blacklist prevents backtest-in-backtest
- Network access blocked
- Cannot read raw dataset files (must use API)
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import traceback
import types
from pathlib import Path
from typing import Any

from traderharness.tools.registry import ToolDefinition, ToolContext
from traderharness.agents.sandbox.api import build_api_module

SANDBOX_TIMEOUT = 60

BLOCKED_IMPORTS = {
    "traderharness", "backtrader", "vnpy", "zipline", "qlib",
    "pyalgotrade", "bt", "finrl",
}


def _resolve_safe_path(workspace_root: str, relative_path: str) -> Path | None:
    """Resolve path within workspace. Returns None if escape attempted."""
    root = Path(workspace_root).resolve()
    # Reject absolute paths
    if os.path.isabs(relative_path):
        return None
    target = (root / relative_path).resolve()
    # Ensure target is within workspace
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


async def handle_write_file(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", "")
    content = params.get("content", "")
    if not path:
        return {"error": "path 不能为空"}

    target = _resolve_safe_path(ctx.workspace_root, path)
    if target is None:
        return {"error": f"路径不安全，不能超出工作目录: {path}"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"success": True, "path": path, "size": len(content)}


async def handle_read_file(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", "")
    if not path:
        return {"error": "path 不能为空"}

    target = _resolve_safe_path(ctx.workspace_root, path)
    if target is None:
        return {"error": f"路径不安全，不能超出工作目录: {path}"}

    if not target.exists():
        return {"error": f"文件不存在: {path}"}

    content = target.read_text(encoding="utf-8", errors="replace")
    if len(content) > 10000:
        content = content[:10000] + "\n... (truncated, total " + str(len(content)) + " chars)"
    return {"content": content, "path": path, "size": target.stat().st_size}


async def handle_list_files(params: dict, ctx: ToolContext) -> dict:
    path = params.get("path", ".")
    target = _resolve_safe_path(ctx.workspace_root, path)
    if target is None:
        return {"error": f"路径不安全: {path}"}

    if not target.exists():
        return {"error": f"目录不存在: {path}"}

    if not target.is_dir():
        return {"error": f"不是目录: {path}"}

    files = []
    for item in sorted(target.iterdir()):
        name = item.name + ("/" if item.is_dir() else "")
        files.append(name)

    return {"path": path, "files": files, "count": len(files)}


async def handle_run_python(params: dict, ctx: ToolContext) -> dict:
    code = params.get("code", "")
    if not code.strip():
        return {"error": "code 不能为空"}

    # Check for blocked imports before execution
    block_error = _check_blocked_imports(code)
    if block_error:
        return {"error": block_error}

    # Build API module
    api_module = build_api_module(ctx)
    fake_module = types.ModuleType("traderharness_api")
    fake_module.market = api_module["market"]
    fake_module.portfolio = api_module["portfolio"]
    fake_module.news = api_module["news"]

    # Save and restore sys.modules
    old_modules = {}
    if "traderharness_api" in sys.modules:
        old_modules["traderharness_api"] = sys.modules["traderharness_api"]
    sys.modules["traderharness_api"] = fake_module

    # Install import hook to block dangerous imports
    blocker = _ImportBlocker()
    sys.meta_path.insert(0, blocker)

    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    old_cwd = os.getcwd()
    result_value: Any = None
    error_msg: str | None = None

    try:
        # Change to workspace directory so relative file ops work
        workspace = Path(ctx.workspace_root)
        workspace.mkdir(parents=True, exist_ok=True)
        os.chdir(workspace)

        sys.stdout = stdout_capture
        from traderharness.agents.sandbox.guard import build_sandbox_globals
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


def _check_blocked_imports(code: str) -> str | None:
    """Static check for blocked imports before execution."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # Let runtime handle syntax errors

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in BLOCKED_IMPORTS:
                    return f"禁止导入 '{alias.name}'。沙箱内不能使用回测框架，请通过 traderharness_api 访问数据。"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in BLOCKED_IMPORTS:
                    return f"禁止导入 '{node.module}'。沙箱内不能使用回测框架，请通过 traderharness_api 访问数据。"
    return None


class _ImportBlocker:
    """sys.meta_path hook that blocks dangerous imports at runtime."""

    def find_module(self, fullname, path=None):
        root = fullname.split(".")[0]
        if root in BLOCKED_IMPORTS:
            return self
        return None

    def load_module(self, fullname):
        raise ImportError(f"Module '{fullname}' is blocked in sandbox")


# Tool definitions

WRITE_FILE = ToolDefinition(
    name="write_file",
    description="写文件到工作目录。可用于保存分析笔记、策略代码、计算结果。路径相对于工作目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对于工作目录），如 notes/analysis.md"},
            "content": {"type": "string", "description": "文件内容"},
        },
        "required": ["path", "content"],
    },
    handler=handle_write_file,
)

READ_FILE = ToolDefinition(
    name="read_file",
    description="读取工作目录中的文件。可读取之前保存的笔记、策略代码等。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对于工作目录）"},
        },
        "required": ["path"],
    },
    handler=handle_read_file,
)

LIST_FILES = ToolDefinition(
    name="list_files",
    description="列出工作目录中的文件和子目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径（相对于工作目录），默认为根目录", "default": "."},
        },
        "required": [],
    },
    handler=handle_list_files,
)

RUN_PYTHON = ToolDefinition(
    name="run_python",
    description=(
        "在工作目录中执行Python代码。通过 `from traderharness_api import market, portfolio, news` "
        "访问市场数据（严格遮罩）。可 import numpy/pandas/scipy。"
        "工作目录内的文件可直接 open() 读写。超时60秒。将结果赋值给 `result` 变量可在返回值中看到。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python 代码"},
        },
        "required": ["code"],
    },
    handler=handle_run_python,
)
