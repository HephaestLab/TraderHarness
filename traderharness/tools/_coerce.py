"""Numeric coercion helpers shared by tool handlers and the sandbox API.

Upstream feeds occasionally emit NaN/inf for missing quote fields (e.g. a
halted stock's volume). Agent-facing handlers must degrade to a default
instead of raising inside a tool call.
"""

from __future__ import annotations

import math


def safe_int(value, default: int = 0) -> int:
    """Convert a possibly-missing/NaN/inf scalar to int without raising."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return int(number)


def safe_float(value, default: float = 0.0) -> float:
    """Convert a possibly-missing/NaN/inf scalar to float without raising."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number
