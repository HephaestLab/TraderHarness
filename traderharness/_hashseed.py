"""Fixed hash seed for cross-process replay determinism.

Agent sandbox code executes in-process (``traderharness.tools.sandbox``), so
Python's string hash randomization leaks into agent-visible output: ``set``
iteration order differs between processes, which changes sandbox tool output
text, which changes LLM request fingerprints — a cassette recorded in one
process then fails to replay in any other (observed as
``ReplayMismatchError`` at the first set-order-sensitive tool result).

Entry points (CLI group, pytest conftest) call :func:`ensure_fixed_hash_seed`
before anything else: when ``PYTHONHASHSEED`` is not already pinned, the
process re-runs itself with ``PYTHONHASHSEED=0`` and forwards the child's
exit code. ``subprocess.call`` is used instead of ``os.execv`` so exit codes
survive on Windows (MSVCRT ``_execv`` does not propagate them reliably). Any
explicitly configured value is respected as-is — recording and replay both
go through the same entry points, so one pinned value is enough.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _rerun_command() -> list[str]:
    """Rebuild the current invocation in an interpreter-direct form.

    ``sys.argv[0]`` may point at a console_script binary (``traderharness.exe``)
    that ``python.exe`` cannot execute as a script, so route those through the
    package's ``-m`` entry point instead.
    """
    argv0 = sys.argv[0] if sys.argv else ""
    base = os.path.basename(argv0).lower()
    if base.endswith(".py"):
        return [sys.executable, *sys.argv]
    if base.startswith("pytest"):
        return [sys.executable, "-m", "pytest", *sys.argv[1:]]
    return [sys.executable, "-m", "traderharness", *sys.argv[1:]]


def ensure_fixed_hash_seed() -> None:
    """Re-run the current process with a pinned PYTHONHASHSEED, if unset."""
    if "PYTHONHASHSEED" in os.environ:
        return
    env = dict(os.environ, PYTHONHASHSEED="0")
    try:
        raise SystemExit(subprocess.call(_rerun_command(), env=env))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
