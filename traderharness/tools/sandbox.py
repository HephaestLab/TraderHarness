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
import ctypes
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import types
from pathlib import Path
from typing import Any

from traderharness.agents.sandbox.api import build_api_module
from traderharness.agents.sandbox.guard import build_sandbox_globals
from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition

SANDBOX_TIMEOUT = 60
_LEGACY_EXEC_TRACEBACK_LINE = 151

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
                    return f"禁止导入 '{alias.name}'。沙箱内不能使用回测框架，请通过 traderharness_api 访问数据。"
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_IMPORTS:
                return f"禁止导入 '{node.module}'。沙箱内不能使用回测框架，请通过 traderharness_api 访问数据。"
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


def _interrupt_thread(thread: threading.Thread) -> bool:
    """Stop timed-out Python bytecode and confirm that the worker exited."""
    if thread.ident is None or not thread.is_alive():
        return True
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread.ident),
        ctypes.py_object(SystemExit),
    )
    if result > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), None)
        return False
    thread.join(timeout=2)
    return not thread.is_alive()


def _normalize_legacy_traceback(value: str) -> str:
    """Keep v1-v4 cassette fingerprints stable after the v5 timeout guard moved code."""
    return re.sub(
        r'(File "[^\"]*traderharness[\\/]tools[\\/]sandbox\.py", line )\d+(, in _run)',
        rf"\g<1>{_LEGACY_EXEC_TRACEBACK_LINE}\g<2>",
        value,
    )


async def handle_execute_code(params: dict, ctx: ToolContext) -> dict:
    current_contract = is_current_contract(getattr(ctx, "tool_contract_version", None))
    limit = max(0, int(getattr(ctx, "sandbox_max_calls_per_day", 0)))
    calls = int(ctx.tool_call_cache.get("_sandbox_call_count", 0))
    if limit and calls >= limit:
        result = {
            "error": (
                f"execute_code daily limit reached ({limit}); use ordinary allowed tools "
                "to validate and register the final candidates"
            )
        }
        if current_contract:
            result.update(
                {
                    "success": False,
                    "error_code": "sandbox_daily_limit_reached",
                    "retryable": False,
                    "correction": {
                        "instruction": "今日停止代码研究，改用当前阶段暴露的普通工具。",
                        "daily_limit": limit,
                        "calls_used": calls,
                    },
                }
            )
        return result
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
            deadline = time.monotonic() + SANDBOX_TIMEOUT

            def _deadline_trace(frame, event, arg):
                if time.monotonic() > deadline:
                    raise TimeoutError(f"执行超时（{SANDBOX_TIMEOUT}秒限制）")
                return _deadline_trace

            try:
                sys.settrace(_deadline_trace)
                exec(compile(code, "<agent_code>", "exec"), exec_globals)
                if "result" in exec_globals:
                    result_value = exec_globals["result"]
            except TimeoutError as exc:
                error_msg = f"{exc}；后台执行已终止"
            except ImportError as e:
                if any(blocked in str(e) for blocked in BLOCKED_IMPORTS):
                    error_msg = f"禁止导入: {e}。沙箱内不能使用回测框架。"
                else:
                    error_msg = traceback.format_exc()
            except Exception:
                error_msg = traceback.format_exc()
            finally:
                sys.settrace(None)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=SANDBOX_TIMEOUT)

        if thread.is_alive():
            terminated = _interrupt_thread(thread)
            error_msg = (
                f"执行超时（{SANDBOX_TIMEOUT}秒限制）；后台执行已终止"
                if terminated
                else f"执行超时（{SANDBOX_TIMEOUT}秒限制）；后台线程未能安全终止"
            )

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
        if not current_contract:
            error_msg = _normalize_legacy_traceback(error_msg)
        response["error"] = error_msg
        if current_contract:
            timed_out = "执行超时" in error_msg
            attempts_after_this = calls + 1
            retryable = not limit or attempts_after_this < limit
            response.update(
                {
                    "success": False,
                    "error_code": "sandbox_timeout" if timed_out else "sandbox_execution_failed",
                    "retryable": retryable,
                    "correction": {
                        "instruction": (
                            "读取 traceback 的最后一行和 <agent_code> 行号，只修正同一分析目标后重试。"
                            if retryable
                            else "代码调用预算已耗尽；使用普通工具继续，不要重试。"
                        ),
                        "attempts_used_after_call": attempts_after_this,
                        "daily_limit": limit or None,
                    },
                }
            )
    if result_value is not None:
        try:
            response["result"] = json.loads(json.dumps(result_value, default=str))
        except (TypeError, ValueError):
            response["result"] = str(result_value)[:2000]

    if not response:
        response["stdout"] = "(no output)"

    # Count executed attempts, not only successful programs.  Otherwise an LLM
    # can retry failing code indefinitely without consuming the configured
    # daily budget.  The loop uses the last-error marker to expose one bounded
    # traceback-driven correction when the Agent card grants a second attempt.
    ctx.tool_call_cache["_sandbox_call_count"] = calls + 1
    ctx.tool_call_cache["_sandbox_last_error"] = error_msg is not None

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
    handler_masks_egress=True,
)
