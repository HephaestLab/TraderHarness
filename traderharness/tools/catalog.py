"""Public tool catalog and Agent Card allowlist policy."""

from __future__ import annotations

from typing import Any

TOOL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "get_kline",
        "label": "K 线历史",
        "description": "查询严格按时间点遮罩的日线与分钟 OHLCV。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_stock_price",
        "label": "最新可见价格",
        "description": "读取当前时间窗口内最新可用价格。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_stock_info",
        "label": "证券资料",
        "description": "查询已遮罩名称、行业、上市板块和市场元数据。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_market_overview",
        "label": "市场宽度",
        "description": "查看涨跌家数以及领涨、领跌行业。",
        "category": "market",
        "required": False,
    },
    {
        "name": "screen_stocks",
        "label": "条件选股",
        "description": "根据价格、动量等条件筛选当前可见股票池。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_sector_summary",
        "label": "行业概览",
        "description": "比较各行业在当前时间点的强弱与成分股。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_fundamentals",
        "label": "基本面",
        "description": "查询当时已发布的盈利能力与成长指标。",
        "category": "fundamental",
        "required": False,
    },
    {
        "name": "get_business_segments",
        "label": "主营构成",
        "description": "查询产品与地区维度的收入构成。",
        "category": "fundamental",
        "required": False,
    },
    {
        "name": "get_valuation",
        "label": "估值",
        "description": "查询时间点安全的 PE、PB、PS 和换手率。",
        "category": "fundamental",
        "required": False,
    },
    {
        "name": "get_announcements",
        "label": "公司公告",
        "description": "研究当时已公开的上市公司公告。",
        "category": "information",
        "required": False,
    },
    {
        "name": "get_news",
        "label": "市场新闻",
        "description": "搜索当前可见的政策与市场新闻。",
        "category": "information",
        "required": False,
    },
    {
        "name": "get_portfolio",
        "label": "账户组合",
        "description": "读取现金、持仓和当前风险敞口。",
        "category": "portfolio",
        "required": True,
    },
    {
        "name": "get_position",
        "label": "持仓明细",
        "description": "查询单个当前持仓及其成本。",
        "category": "portfolio",
        "required": True,
    },
    {
        "name": "place_order",
        "label": "下单",
        "description": "通过唯一受保护的下单与撮合路径执行交易。",
        "category": "execution",
        "required": True,
    },
    {
        "name": "add_watchlist",
        "label": "加入自选",
        "description": "将证券加入可跨交易日保留的自选列表。",
        "category": "workflow",
        "required": False,
    },
    {
        "name": "remove_watchlist",
        "label": "移出自选",
        "description": "从自选列表中移除证券。",
        "category": "workflow",
        "required": False,
    },
    {
        "name": "get_watchlist",
        "label": "查询自选",
        "description": "查看当前跨交易日自选列表。",
        "category": "workflow",
        "required": False,
    },
    {
        "name": "execute_code",
        "label": "Python 研究",
        "description": "在已遮罩的内存数据上执行受保护分析。",
        "category": "quant",
        "required": False,
    },
    {
        "name": "finish_day",
        "label": "结束交易日",
        "description": "提交每日总结并推进市场时钟。",
        "category": "execution",
        "required": True,
    },
)

ALL_TOOL_NAMES = frozenset(item["name"] for item in TOOL_CATALOG)
CORE_TOOL_NAMES = frozenset(item["name"] for item in TOOL_CATALOG if item["required"])


def normalize_allowed_tools(tools: list[str] | tuple[str, ...] | None) -> list[str]:
    """Validate a card allowlist and restore the protected execution core."""
    requested = ALL_TOOL_NAMES if tools is None else {str(name) for name in tools}
    unknown = requested - ALL_TOOL_NAMES
    if unknown:
        raise ValueError(f"Unknown Agent tools: {', '.join(sorted(unknown))}")
    allowed = requested | CORE_TOOL_NAMES
    return [item["name"] for item in TOOL_CATALOG if item["name"] in allowed]


def tool_catalog_payload() -> list[dict[str, Any]]:
    return [dict(item) for item in TOOL_CATALOG]
