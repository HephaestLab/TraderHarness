"""Prompt 未来函数审核 — 检测 persona 中是否包含未来信息泄露。

每次 run 自动审核（缓存同 hash prompt），用最便宜模型，发现泄露黄色警告不阻止。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

from traderharness.paths import prompt_audit_cache_dir

_AUDIT_CACHE_DIR = prompt_audit_cache_dir()

AUDIT_PROMPT = """你是一个 prompt 审计系统。请检查以下交易员角色设定是否包含"未来函数"泄露。

未来函数泄露指：
1. 提到了具体的未来日期或事件（如"2024年6月会涨"）
2. 暗示了特定股票的未来走势（如"茅台将突破2000"）
3. 引用了回测开始日之后才发生的政策、新闻或市场事件
4. 任何让 Agent 在回测中拥有"先知"能力的信息

回测开始日期: {backtest_start}
回测结束日期: {backtest_end}

要检查的角色设定:
---
{persona}
---

如果发现泄露，返回 JSON: {{"leak_found": true, "details": "具体说明"}}
如果没有泄露，返回 JSON: {{"leak_found": false, "details": ""}}
"""


async def audit_persona(
    persona: str,
    backtest_start: date,
    backtest_end: date,
    llm_client=None,
) -> dict:
    """审核 persona 是否包含未来信息泄露。

    Returns: {"leak_found": bool, "details": str, "cached": bool}
    """
    cache_key = hashlib.sha256(
        f"{persona}|{backtest_start}|{backtest_end}".encode()
    ).hexdigest()

    cached = _get_cached(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    if llm_client is None:
        return {"leak_found": False, "details": "no LLM client for audit", "cached": False}

    prompt = AUDIT_PROMPT.format(
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        persona=persona,
    )

    try:
        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.get("content", "")
        result = _parse_audit_result(content)
    except Exception as e:
        logger.warning("prompt_audit_failed: %s", e)
        result = {"leak_found": False, "details": f"audit failed: {e}"}

    _save_cache(cache_key, result)
    result["cached"] = False

    if result.get("leak_found"):
        logger.warning(
            "PROMPT AUDIT WARNING: 检测到未来信息泄露! %s", result["details"]
        )

    return result


def _parse_audit_result(content: str) -> dict:
    try:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        if "leak_found" in content and "true" in content.lower():
            return {"leak_found": True, "details": content}
        return {"leak_found": False, "details": ""}


def _get_cached(key: str) -> dict | None:
    path = _AUDIT_CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_cache(key: str, result: dict) -> None:
    _AUDIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _AUDIT_CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
