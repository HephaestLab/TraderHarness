"""Stock registry loader — loads industry/name data from cached JSON.

Uses the stock_registry.json exported from the source project
(5937 stocks with industry classification).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "stock_registry.json"
_registry: dict[str, dict] | None = None


def is_a_share_stock_code(code: str) -> bool:
    code = str(code).strip()
    if len(code) != 6 or not code.isdigit():
        return False
    return code.startswith(
        (
            "000",
            "001",
            "002",
            "003",
            "300",
            "301",
            "600",
            "601",
            "603",
            "605",
            "688",
            "689",
            "4",
            "8",
            "920",
        )
    )


def _load_registry() -> dict[str, dict]:
    global _registry
    if _registry is not None:
        return _registry
    if _REGISTRY_PATH.exists():
        raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        _registry = {
            code: {
                key: (value.replace("\x00", "").strip() if isinstance(value, str) else value)
                for key, value in info.items()
            }
            for code, info in raw.items()
        }
        logger.info("stock_registry loaded: %d stocks", len(_registry))
    else:
        _registry = {}
        logger.warning("stock_registry.json not found at %s", _REGISTRY_PATH)
    return _registry


def get_stock_info(code: str) -> dict:
    """Get stock info: {name, industry, market}."""
    reg = _load_registry()
    return reg.get(code, {"name": code, "industry": "其他", "market": "主板"})


def get_stock_registry() -> dict[str, dict]:
    """Return listed A-share stocks, excluding indices and funds."""
    return {code: info for code, info in _load_registry().items() if is_a_share_stock_code(code)}


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
