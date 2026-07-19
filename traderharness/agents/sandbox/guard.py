"""Sandbox execution guard — confines agent code to its workspace.

The sandbox lets the agent run arbitrary Python (numpy/pandas/etc.), but it must
NOT be able to reach the raw dataset on disk, otherwise every look-ahead /
date-masking protection is bypassed by a single ``pd.read_parquet(...)``.

This module builds the ``exec`` globals used by ``execute_code``:

- ``open`` is replaced by a workspace-scoped variant.
- ``pandas`` / ``numpy`` file readers are wrapped to reject paths outside the
  workspace.
- A curated ``__import__`` blocks filesystem/OS/network escape modules while
  leaving the analysis toolkit (numpy, pandas, scipy, math, ...) available.

No global module state is mutated (the guarded pandas/numpy are per-call
proxies), so concurrent multi-agent runs are unaffected.
"""

from __future__ import annotations

import builtins as _builtins
from pathlib import Path
from typing import Any

# Modules the agent may not import: OS / filesystem / network escape hatches
# plus backtest frameworks (running a backtest inside the backtest).
BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        # filesystem / OS / process
        "os",
        "sys",
        "subprocess",
        "shutil",
        "glob",
        "pathlib",
        "tempfile",
        "fileinput",
        "importlib",
        "ctypes",
        "mmap",
        "pickle",
        "marshal",
        # network
        "socket",
        "urllib",
        "requests",
        "httpx",
        "ftplib",
        "smtplib",
        "http",
        # backtest frameworks
        "traderharness",
        "backtrader",
        "vnpy",
        "zipline",
        "qlib",
        "pyalgotrade",
        "bt",
        "finrl",
    }
)

# pandas readers that touch the filesystem
_PANDAS_READERS: frozenset[str] = frozenset(
    {
        "read_parquet",
        "read_csv",
        "read_table",
        "read_feather",
        "read_pickle",
        "read_hdf",
        "read_json",
        "read_orc",
        "read_excel",
        "read_stata",
        "read_sas",
        "read_spss",
        "read_xml",
        "read_html",
        "read_fwf",
        "read_sql",
        "read_sql_table",
    }
)

# numpy readers that touch the filesystem
_NUMPY_READERS: frozenset[str] = frozenset(
    {
        "load",
        "loadtxt",
        "genfromtxt",
        "fromfile",
        "memmap",
        "fromregex",
    }
)


def _path_within(path: Any, root: Path) -> bool:
    """True if ``path`` resolves to something inside ``root``."""
    if not isinstance(path, (str, bytes, Path)):
        # file-like objects / buffers are in-memory — allow
        return True
    try:
        p = Path(path.decode() if isinstance(path, bytes) else path)
        if not p.is_absolute():
            p = root / p
        p = p.resolve()
        return p == root or root in p.parents
    except (OSError, ValueError):
        return False


class _GuardedModule:
    """Attribute proxy that wraps a module's file-reading functions."""

    def __init__(self, real: Any, readers: frozenset[str], root: Path) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_readers", readers)
        object.__setattr__(self, "_root", root)

    def __getattr__(self, name: str) -> Any:
        real = object.__getattribute__(self, "_real")
        readers = object.__getattribute__(self, "_readers")
        root = object.__getattribute__(self, "_root")
        attr = getattr(real, name)
        if name in readers and callable(attr):

            def guarded(path: Any = None, *args: Any, **kwargs: Any) -> Any:
                if path is not None and not _path_within(path, root):
                    raise PermissionError(f"沙箱只能访问工作目录内的文件，禁止读取: {path}")
                return attr(path, *args, **kwargs)

            return guarded
        return attr


def build_sandbox_globals(fake_api_module: Any, workspace_root: str) -> dict:
    """Build the ``exec`` globals for sandboxed agent code."""
    root = Path(workspace_root).resolve()

    safe_builtins = dict(vars(_builtins))

    def safe_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):
        if not _path_within(file, root):
            raise PermissionError(f"沙箱只能访问工作目录内的文件，禁止: {file}")
        p = Path(file)
        if not p.is_absolute():
            p = root / p
        if any(m in mode for m in ("w", "a", "x", "+")):
            p.parent.mkdir(parents=True, exist_ok=True)
        return _builtins.open(p, mode, *args, **kwargs)

    import numpy as _np
    import pandas as _pd

    guarded_pd = _GuardedModule(_pd, _PANDAS_READERS, root)
    guarded_np = _GuardedModule(_np, _NUMPY_READERS, root)

    def guarded_import(name: str, globals=None, locals=None, fromlist=(), level=0):
        top = name.split(".")[0]
        if top in BLOCKED_IMPORTS:
            raise ImportError(
                f"禁止导入: {name}（沙箱内不可用，请通过 traderharness_api 访问数据）"
            )
        if name == "pandas":
            return guarded_pd
        if name == "numpy":
            return guarded_np
        return _builtins.__import__(name, globals, locals, fromlist, level)

    safe_builtins["open"] = safe_open
    safe_builtins["__import__"] = guarded_import

    return {
        "__builtins__": safe_builtins,
        "traderharness_api": fake_api_module,
        "pd": guarded_pd,
        "pandas": guarded_pd,
        "np": guarded_np,
        "numpy": guarded_np,
    }
