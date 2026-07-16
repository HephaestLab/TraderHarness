"""新闻公告工具 — get_announcements, get_news。"""

from __future__ import annotations

from datetime import timedelta

from traderharness.tools.registry import ToolDefinition, ToolContext


async def handle_get_announcements(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    days = min(params.get("days", 30), 90)

    if not code:
        return {"error": "stock_code 不能为空"}

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
        return {"stock_code": code, "announcements": [], "count": 0, "hint": f"{code} 近{days}天无公告"}

    results = []
    for _, row in filtered.tail(20).iterrows():
        results.append({
            "title": row["title"],
        })

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

    filtered = news_data[
        (news_data["display_time"].dt.date >= start)
        & (news_data["display_time"].dt.date < cutoff)
    ]

    # Filter by stock_code (from stock_list column if available)
    if stock_code and "stock_list" in filtered.columns:
        filtered = filtered[filtered["stock_list"].str.contains(stock_code, na=False)]

    # Filter by sector/keyword
    search_terms = []
    if keyword:
        search_terms.append(keyword)
    if sector:
        search_terms.append(sector)

    if search_terms:
        pattern = "|".join(search_terms)
        filtered = filtered[filtered["content"].str.contains(pattern, na=False)]

    if filtered.empty:
        hint = f"近{days}天无"
        if keyword or sector:
            hint += f"含「{keyword or sector}」的"
        hint += "快讯"
        return {"news": [], "count": 0, "hint": hint}

    results = []
    for _, row in filtered.tail(15).iterrows():
        results.append({
            "content": row["content"][:100],
            "level": row.get("level", ""),
        })

    filter_desc = keyword or sector or "(全部)"
    return {"news": results, "count": len(filtered), "filter": filter_desc}


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
