"""Python 受限执行沙箱 — 安全地运行 Agent 写的分析代码。

从源项目 backend/agents/agentic/sandbox.py 完整迁移。
包含 AST 安全检查 + 线程超时。
"""

from __future__ import annotations

import ast
import io
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_MODULES = frozenset({
    "math", "statistics", "decimal", "datetime", "collections",
    "json", "re", "itertools", "functools", "operator",
})

FORBIDDEN_NAMES = frozenset({
    "exec", "eval", "compile", "__import__", "globals", "locals",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit",
})

FORBIDDEN_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "requests",
    "httpx", "urllib", "ftplib", "smtplib", "signal", "ctypes",
    "multiprocessing", "threading",
})


@dataclass
class SandboxResult:
    stdout: str
    result: Any
    error: str | None


class PythonSandbox:
    """受限 Python 执行环境。"""

    MAX_EXECUTION_TIME = 10
    MAX_OUTPUT_SIZE = 8192

    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace = workspace_root

    def execute(
        self, code: str, injected_data: dict[str, Any] | None = None
    ) -> SandboxResult:
        error = self._check_ast(code)
        if error:
            return SandboxResult(stdout="", result=None, error=error)

        namespace = self._build_namespace(injected_data)

        stdout_capture = io.StringIO()
        result = [None]
        exec_error = [None]

        def _run():
            old_stdout = sys.stdout
            try:
                sys.stdout = stdout_capture
                exec(compile(code, "<agent_script>", "exec"), namespace)
                if "_result_" in namespace:
                    result[0] = namespace["_result_"]
            except Exception as e:
                exec_error[0] = f"{type(e).__name__}: {str(e)}"
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.MAX_EXECUTION_TIME)

        if thread.is_alive():
            return SandboxResult(
                stdout="", result=None,
                error=f"执行超时（>{self.MAX_EXECUTION_TIME}秒）"
            )

        stdout = stdout_capture.getvalue()
        if len(stdout) > self.MAX_OUTPUT_SIZE:
            stdout = stdout[:self.MAX_OUTPUT_SIZE] + "\n... (输出截断)"

        return SandboxResult(stdout=stdout, result=result[0], error=exec_error[0])

    def _check_ast(self, code: str) -> str | None:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"语法错误: {e}"

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(node, ast.Import):
                    module = node.names[0].name.split(".")[0]
                elif node.module:
                    module = node.module.split(".")[0]
                if module in FORBIDDEN_MODULES:
                    return f"禁止导入模块: {module}"
                if module not in ALLOWED_MODULES and module not in ("pandas", "numpy"):
                    return f"不允许的模块: {module}（可用: pandas, numpy, math, statistics, json, datetime, collections）"

            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
                    return f"禁止调用: {node.func.id}"
                if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                    return "禁止调用 os.system"

        return None

    def _build_namespace(self, injected_data: dict[str, Any] | None = None) -> dict:
        import math
        import statistics
        import decimal
        import datetime
        import collections
        import json as json_mod

        def _safe_import(name, *args, **kwargs):
            top = name.split(".")[0]
            if top in FORBIDDEN_MODULES:
                raise ImportError(f"禁止导入模块: {top}")
            if top not in ALLOWED_MODULES and top not in ("pandas", "numpy"):
                raise ImportError(f"不允许的模块: {top}")
            import importlib
            return importlib.import_module(name)

        safe_builtins = {
            "__import__": _safe_import,
            "print": print, "len": len, "range": range, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter, "sorted": sorted,
            "reversed": reversed, "min": min, "max": max, "sum": sum,
            "abs": abs, "round": round, "int": int, "float": float,
            "str": str, "bool": bool, "list": list, "dict": dict,
            "tuple": tuple, "set": set, "type": type, "isinstance": isinstance,
            "True": True, "False": False, "None": None,
            "ValueError": ValueError, "TypeError": TypeError,
            "KeyError": KeyError, "IndexError": IndexError,
        }

        namespace = {
            "__builtins__": safe_builtins,
            "math": math, "statistics": statistics, "decimal": decimal,
            "datetime": datetime, "collections": collections, "json": json_mod,
        }

        try:
            import pandas as pd
            namespace["pd"] = pd
            namespace["pandas"] = pd
        except ImportError:
            pass

        try:
            import numpy as np
            namespace["np"] = np
            namespace["numpy"] = np
        except ImportError:
            pass

        if injected_data:
            namespace.update(injected_data)

        if self._workspace:
            workspace = self._workspace

            def safe_open(path, mode="r", **kwargs):
                resolved = (workspace / path).resolve()
                if not str(resolved).startswith(str(workspace.resolve())):
                    raise PermissionError("只能访问工作目录内的文件")
                if "w" in mode or "a" in mode:
                    resolved.parent.mkdir(parents=True, exist_ok=True)
                return open(resolved, mode, encoding="utf-8", **kwargs)

            namespace["__builtins__"]["open"] = safe_open

        return namespace
