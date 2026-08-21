"""新闻公告工具 — get_announcements, get_news。"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from traderharness.data.stock_registry_loader import get_stock_name
from traderharness.tools.contracts import is_current_contract
from traderharness.tools.registry import ToolContext, ToolDefinition


def _masked_time(ctx: ToolContext, value) -> str:
    masker = getattr(ctx, "date_masker", None)
    return masker.mask_datetime(value) if masker is not None else str(value)


def _clean_text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _text_contains(frame: pd.DataFrame, term: str) -> pd.Series:
    matched = pd.Series(False, index=frame.index)
    for column in ("title", "content", "tags", "stock_list"):
        if column in frame.columns:
            matched |= frame[column].fillna("").astype(str).str.contains(term, regex=False)
    return matched


def _remember_visible_evidence_ids(ctx: ToolContext, items: list[dict]) -> None:
    visible = ctx.tool_call_cache.setdefault("_visible_text_evidence_ids", set())
    visible.update(str(item["evidence_id"]) for item in items if str(item.get("evidence_id", "")).strip())


async def handle_get_announcement_evidence(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    days = min(params.get("days", 30), 90)

    if not code:
        return {"error": "stock_code 不能为空"}
    from traderharness.agents.window_context import code_in_universe, universe_error

    if not code_in_universe(code, ctx):
        return universe_error(code)

    announcements = ctx.tool_call_cache.get("_announcements_data")
    if announcements is None:
        return {"error": "公告数据未加载"}

    cutoff = ctx.current_date
    start = ctx.current_date - timedelta(days=days)

    filtered = announcements[
        (announcements["stock_code"] == code)
        & (announcements["announcement_time"].dt.date >= start)
        & (announcements["announcement_time"].dt.date < cutoff)
    ]

    if filtered.empty:
        return {
            "stock_code": code,
            "announcements": [],
            "count": 0,
            "hint": f"{code} 近{days}天无公告",
        }

    results = []
    for _, row in filtered.tail(20).iterrows():
        results.append(
            {
                "evidence_id": f"announcement:{code}:{row.name}",
                "time": _masked_time(ctx, row["announcement_time"]),
                "title": _clean_text(row["title"]),
                "type": _clean_text(row.get("ann_type")),
            }
        )

    _remember_visible_evidence_ids(ctx, results)
    return {"stock_code": code, "announcements": results, "count": len(filtered)}


async def handle_get_narrative_news(params: dict, ctx: ToolContext) -> dict:
    days = min(params.get("days", 3), 3)
    keyword = params.get("keyword", "")
    sector = params.get("sector", "")
    stock_code = params.get("stock_code", "")
    max_results = max(1, min(int(params.get("max_results", 15)), 30))
    market_relevant_only = bool(params.get("market_relevant_only", False))

    query_key = (
        days,
        str(keyword),
        str(sector),
        str(stock_code),
        max_results,
        market_relevant_only,
    )
    cache = ctx.tool_call_cache.setdefault("_narrative_news_cache", {})
    if query_key in cache:
        return cache[query_key]
    calls = int(ctx.tool_call_cache.get("_narrative_news_calls", 0))
    if calls >= 2:
        result = {
            "budget_exhausted": True,
            "limit": 2,
            "instruction": "Use the narrative evidence already returned; do not retry today.",
        }
        if is_current_contract(getattr(ctx, "tool_contract_version", None)):
            result.update(
                {
                    "success": False,
                    "error": "叙事新闻工具今日两次查询预算已耗尽。",
                    "error_code": "daily_tool_budget_exhausted",
                    "retryable": False,
                    "correction": {"instruction": "使用今日已经返回的叙事证据继续判断，不要重试。"},
                }
            )
        return result

    news_data = ctx.tool_call_cache.get("_news_data")
    if news_data is None:
        return {"error": "快讯数据未加载"}

    cutoff = ctx.current_date
    start = ctx.current_date - timedelta(days=days)

    filtered = news_data[(news_data["display_time"].dt.date >= start) & (news_data["display_time"].dt.date < cutoff)]

    # The source stock_list commonly contains names rather than codes. Search
    # both so an Agent can link a masked code back to the point-in-time text.
    if stock_code:
        stock_name = get_stock_name(stock_code)
        matched = _text_contains(filtered, stock_code)
        if stock_name and stock_name != stock_code:
            matched |= _text_contains(filtered, stock_name)
        filtered = filtered[matched]

    # Filter by sector/keyword
    search_terms = []
    if keyword:
        search_terms.append(keyword)
    if sector:
        search_terms.append(sector)

    if search_terms:
        matched = pd.Series(False, index=filtered.index)
        for term in search_terms:
            matched |= _text_contains(filtered, str(term))
        filtered = filtered[matched]

    if market_relevant_only and not filtered.empty:
        level = filtered.get("level", pd.Series("", index=filtered.index)).fillna("").astype(str)
        stocks = filtered.get("stock_list", pd.Series("", index=filtered.index)).fillna("").astype(str)
        tags = filtered.get("tags", pd.Series("", index=filtered.index)).fillna("").astype(str)
        filtered = filtered[level.isin({"A", "B"}) | stocks.str.strip().ne("") | tags.str.strip().ne("")]

    if filtered.empty:
        hint = f"近{days}天无"
        if keyword or sector:
            hint += f"含「{keyword or sector}」的"
        hint += "快讯"
        result = {"news": [], "count": 0, "hint": hint}
        cache[query_key] = result
        ctx.tool_call_cache["_narrative_news_calls"] = calls + 1
        return result

    filtered = filtered.sort_values(
        [column for column in ("display_time", "id") if column in filtered.columns],
        kind="stable",
    )
    results = []
    for _, row in filtered.tail(max_results).iterrows():
        evidence_id = row.get("id", row.name)
        results.append(
            {
                "evidence_id": f"news:{evidence_id}",
                "time": _masked_time(ctx, row["display_time"]),
                "title": _clean_text(row.get("title")),
                "content": _clean_text(row.get("content"))[:300],
                "level": _clean_text(row.get("level")),
                "tags": _clean_text(row.get("tags")),
                "linked_stocks": _clean_text(row.get("stock_list")),
            }
        )

    _remember_visible_evidence_ids(ctx, results)
    filter_desc = keyword or sector or "(全部)"
    result = {
        "news": results,
        "count": len(filtered),
        "returned": len(results),
        "filter": filter_desc,
        "as_of_rule": "display_time strictly before current_date",
    }
    cache[query_key] = result
    ctx.tool_call_cache["_narrative_news_calls"] = calls + 1
    return result


async def handle_get_announcements(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    days = min(params.get("days", 30), 90)
    if not code:
        return {"error": "stock_code 不能为空"}
    from traderharness.agents.window_context import code_in_universe, universe_error

    if not code_in_universe(code, ctx):
        return universe_error(code)
    announcements = ctx.tool_call_cache.get("_announcements_data")
    if announcements is None:
        return {"error": "公告数据未加载"}
    cutoff = ctx.current_date
    start = ctx.current_date - timedelta(days=days)
    filtered = announcements[
        (announcements["stock_code"] == code)
        & (announcements["announcement_time"].dt.date >= start)
        & (announcements["announcement_time"].dt.date < cutoff)
    ]
    if filtered.empty:
        return {
            "stock_code": code,
            "announcements": [],
            "count": 0,
            "hint": f"{code} 近{days}天无公告",
        }
    if is_current_contract(getattr(ctx, "tool_contract_version", None)):
        results = [
            {
                "time": _masked_time(ctx, row["announcement_time"]),
                "title": _clean_text(row.get("title")),
                "type": _clean_text(row.get("ann_type")),
            }
            for _, row in filtered.tail(20).iterrows()
        ]
    else:
        results = [{"title": row["title"]} for _, row in filtered.tail(20).iterrows()]
    return {"stock_code": code, "announcements": results, "count": len(filtered)}


async def handle_get_news(params: dict, ctx: ToolContext) -> dict:
    days = min(params.get("days", 3), 3)
    keyword = params.get("keyword", "")
    sector = params.get("sector", "")
    stock_code = params.get("stock_code", "")
    news_data = ctx.tool_call_cache.get("_news_data")
    if news_data is None:
        return {"error": "快讯数据未加载"}
    cutoff = ctx.current_date
    start = ctx.current_date - timedelta(days=days)
    filtered = news_data[(news_data["display_time"].dt.date >= start) & (news_data["display_time"].dt.date < cutoff)]
    current_contract = is_current_contract(getattr(ctx, "tool_contract_version", None))
    if stock_code:
        if current_contract:
            stock_name = get_stock_name(stock_code)
            matched = _text_contains(filtered, stock_code)
            if stock_name and stock_name != stock_code:
                matched |= _text_contains(filtered, stock_name)
            filtered = filtered[matched]
        elif "stock_list" in filtered.columns:
            filtered = filtered[filtered["stock_list"].str.contains(stock_code, na=False)]
    search_terms = []
    if keyword:
        search_terms.append(keyword)
    if sector:
        search_terms.append(sector)
    if search_terms:
        if current_contract:
            matched = pd.Series(False, index=filtered.index)
            for term in search_terms:
                matched |= _text_contains(filtered, str(term))
            filtered = filtered[matched]
        else:
            pattern = "|".join(search_terms)
            filtered = filtered[filtered["content"].str.contains(pattern, na=False)]
    if filtered.empty:
        hint = f"近{days}天无"
        if keyword or sector:
            hint += f"含「{keyword or sector}」的"
        return {"news": [], "count": 0, "hint": hint + "快讯"}
    if current_contract:
        results = [
            {
                "time": _masked_time(ctx, row["display_time"]),
                "title": _clean_text(row.get("title")),
                "content": _clean_text(row.get("content"))[:300],
                "level": _clean_text(row.get("level")),
            }
            for _, row in filtered.tail(15).iterrows()
        ]
    else:
        results = [
            {"content": row["content"][:100], "level": row.get("level", "")} for _, row in filtered.tail(15).iterrows()
        ]
    return {
        "news": results,
        "count": len(filtered),
        "filter": keyword or sector or "(全部)",
    }


GET_ANNOUNCEMENTS = ToolDefinition(
    name="get_announcements",
    description="查询某只股票的近期公告列表（标题+时间）",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "days": {"type": "integer", "description": "查看最近N天的公告，默认30，最大90"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_announcements,
)

GET_ANNOUNCEMENT_EVIDENCE = ToolDefinition(
    name="get_announcement_evidence",
    description="查询个股公告证据，返回证据编号、点时时间、标题和公告类型。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
            "days": {"type": "integer", "description": "查看最近N天，默认30，最大90"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_announcement_evidence,
)

GET_NEWS = ToolDefinition(
    name="get_news",
    description="查询近期财经快讯。可按关键词、板块、个股过滤。",
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "查看最近N天，默认3，最大3"},
            "keyword": {"type": "string", "description": "关键词过滤（如：降准、新能源、芯片）"},
            "sector": {"type": "string", "description": "板块/行业过滤（如：汽车、电力、医药）"},
            "stock_code": {"type": "string", "description": "个股代码过滤（返回提及该股票的快讯）"},
        },
        "required": [],
    },
    handler=handle_get_news,
)

GET_NARRATIVE_NEWS = ToolDefinition(
    name="get_narrative_news",
    description="查询可审计的财经文本证据，返回证据编号、点时时间、标题、正文、标签和关联股票。",
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "查看最近N天，默认3，最大3"},
            "keyword": {"type": "string", "description": "关键词过滤"},
            "sector": {"type": "string", "description": "板块或行业过滤"},
            "stock_code": {"type": "string", "description": "个股代码过滤"},
            "market_relevant_only": {
                "type": "boolean",
                "description": "仅保留A/B级或带标签、板块、关联股票的市场相关快讯",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "description": "最多返回数量，默认15",
            },
        },
        "required": [],
    },
    handler=handle_get_narrative_news,
)
