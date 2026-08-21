"""Public tool catalog and Agent Card allowlist policy."""

from __future__ import annotations

from typing import Any

from traderharness.tools.contracts import TOOL_EXAMPLES, TOOL_RESULT_SUMMARIES

TOOL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "name": "get_kline",
        "label": "K 线历史",
        "description": "查询严格早于当前交易日的日线 OHLCV；分钟线由窗口消息或沙箱方法提供。",
        "category": "market",
        "required": False,
    },
    {
        "name": "get_stock_price",
        "label": "最新可见价格",
        "description": "盘前读取D-1日线，盘中读取当前已揭示子窗口的最新5分钟收盘价。",
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
        "name": "get_narrative_market_overview",
        "label": "叙事市场宽度",
        "description": "比较行业1/5/20日强度、扩散和高低切候选。",
        "category": "market",
        "required": False,
        "opt_in_only": True,
    },
    {
        "name": "screen_stocks",
        "label": "条件选股",
        "description": "根据价格、动量等条件筛选当前可见股票池。",
        "category": "market",
        "required": False,
    },
    {
        "name": "screen_behavioral_cycle",
        "label": "行为量价周期筛选",
        "description": "用冻结的点时量价公式筛选低位建仓、试盘、洗盘和确认拉升候选。",
        "category": "quant",
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
        "name": "get_narrative_sector_summary",
        "label": "叙事行业概览",
        "description": "比较行业多周期强弱、扩散和板块内龙头地位。",
        "category": "market",
        "required": False,
        "opt_in_only": True,
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
        "name": "get_announcement_evidence",
        "label": "公告证据",
        "description": "读取带证据编号与点时时间的公司公告。",
        "category": "information",
        "required": False,
        "opt_in_only": True,
    },
    {
        "name": "get_news",
        "label": "市场新闻",
        "description": "搜索当前可见的政策与市场新闻。",
        "category": "information",
        "required": False,
    },
    {
        "name": "get_narrative_news",
        "label": "叙事文本证据",
        "description": "读取带证据编号、点时时间、标签与关联股票的新闻。",
        "category": "information",
        "required": False,
        "opt_in_only": True,
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
        "name": "manage_conditional_order",
        "label": "管理条件单",
        "description": "创建、修改或取消由环境按后续5分钟收盘价触发的条件单。",
        "category": "execution",
        "required": False,
    },
    {
        "name": "list_conditional_orders",
        "label": "条件单列表",
        "description": "查询条件单状态、修改版本、触发及失败记录。",
        "category": "execution",
        "required": False,
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
        "name": "remember",
        "label": "写入长期记忆",
        "description": "持久保存假设、事实、风控规则或复盘教训，并保留版本链。",
        "category": "memory",
        "required": False,
    },
    {
        "name": "search_memory",
        "label": "检索记忆",
        "description": "确定性检索未常驻上下文的历史记忆。",
        "category": "memory",
        "required": False,
    },
    {
        "name": "get_memory",
        "label": "读取记忆",
        "description": "按 memory_id 读取完整内容与版本状态。",
        "category": "memory",
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
        "name": "complete_phase",
        "label": "结束当前阶段",
        "description": "显式提交当前阶段结论；成功后市场时钟才推进。",
        "category": "execution",
        "required": False,
        "opt_in_only": True,
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
    requested = (
        {item["name"] for item in TOOL_CATALOG if not item.get("opt_in_only")}
        if tools is None
        else {str(name) for name in tools}
    )
    unknown = requested - ALL_TOOL_NAMES
    if unknown:
        raise ValueError(f"Unknown Agent tools: {', '.join(sorted(unknown))}")
    allowed = requested | CORE_TOOL_NAMES
    return [item["name"] for item in TOOL_CATALOG if item["name"] in allowed]


def tool_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            **item,
            "example_arguments": TOOL_EXAMPLES.get(item["name"]),
            "success_result": TOOL_RESULT_SUMMARIES.get(item["name"]),
            "error_contract": {
                "required": [
                    "success",
                    "error",
                    "error_code",
                    "retryable",
                    "correction",
                ]
            },
        }
        for item in TOOL_CATALOG
    ]
