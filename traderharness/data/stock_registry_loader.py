"""Stock registry loader — loads industry/name data from cached JSON.

Uses the stock_registry.json exported from source project (5937 stocks with industry classification).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "stock_registry.json"
_registry: dict[str, dict] | None = None


def _load_registry() -> dict[str, dict]:
    global _registry
    if _registry is not None:
        return _registry
    if _REGISTRY_PATH.exists():
        _registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        logger.info("stock_registry loaded: %d stocks", len(_registry))
    else:
        _registry = {}
        logger.warning("stock_registry.json not found at %s", _REGISTRY_PATH)
    return _registry


def get_stock_info(code: str) -> dict:
    """Get stock info: {name, industry, market}."""
    reg = _load_registry()
    return reg.get(code, {"name": code, "industry": "其他", "market": "主板"})


def get_stock_industry(code: str) -> str:
    """Get top-level industry for a stock code."""
    info = get_stock_info(code)
    industry = info.get("industry", "其他")
    # Simplify 3-level industry to top level (e.g. "银行业-商业银行-国有大型银行" → "银行业")
    if "-" in industry:
        return industry.split("-")[0]
    return industry or "其他"


def get_stock_name(code: str) -> str:
    """Get stock name."""
    info = get_stock_info(code)
    return info.get("name", code)
