"""PythonSandbox — safe execution of agent-written scripts."""

from __future__ import annotations

import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any


class PythonSandbox:
    """Executes Python code in a restricted environment."""

    _BLOCKED_IMPORTS = {"os", "subprocess", "shutil", "pathlib", "socket", "requests"}

    def __init__(self, allowed_globals: dict[str, Any] | None = None) -> None:
        self._globals = allowed_globals or {}
        self._globals.setdefault("__builtins__", self._safe_builtins())

    def execute(self, code: str, timeout: float = 10.0) -> dict:
        """Execute code and return stdout, stderr, and any error."""
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result: dict[str, Any] = {"stdout": "", "stderr": "", "error": None, "success": True}

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(code, self._globals.copy())
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            result["success"] = False

        result["stdout"] = stdout_buf.getvalue()
        result["stderr"] = stderr_buf.getvalue()
        return result

    @classmethod
    def _safe_builtins(cls) -> dict:
        import builtins

        safe = {}
        allowed = [
            "abs", "all", "any", "bool", "dict", "enumerate", "filter",
            "float", "int", "len", "list", "map", "max", "min", "print",
            "range", "round", "set", "sorted", "str", "sum", "tuple", "zip",
            "True", "False", "None", "isinstance", "type",
        ]
        for name in allowed:
            if hasattr(builtins, name):
                safe[name] = getattr(builtins, name)

        def safe_import(name, *args, **kwargs):
            if name in cls._BLOCKED_IMPORTS:
                raise ImportError(f"Import of '{name}' is not allowed in sandbox")
            return __import__(name, *args, **kwargs)

        safe["__import__"] = safe_import
        return safe
