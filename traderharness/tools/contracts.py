"""Current Agent-facing tool contract helpers.

The historical v1-v4 function schemas are intentionally kept on each
``ToolDefinition`` for replay fingerprint compatibility.  Live v5 runs pass
those definitions through this module to add strict input constraints,
model-visible examples, output documentation, and a deterministic local
validator before a handler is called.
"""

from __future__ import annotations

import copy
import json
import math
from typing import Any

CURRENT_TOOL_CONTRACT_VERSION = "v5"

STOCK_CODE_DESCRIPTION = (
    "证券代码。必须原样复制晨报、行情或其他工具返回的完整可见代码；"
    "实体遮罩开启时使用完整板块前缀别名（如 SHM-000360），不得只提交六位后缀。"
)

TOOL_EXAMPLES: dict[str, dict[str, Any]] = {
    "get_kline": {"stock_code": "SHM-000360", "days": 60},
    "get_stock_price": {"stock_code": "SHM-000360"},
    "get_stock_info": {"stock_code": "SHM-000360"},
    "get_market_overview": {},
    "get_narrative_market_overview": {},
    "screen_stocks": {"change_pct_min": 2, "sort_by": "change_5d", "max_results": 10},
    "screen_behavioral_cycle": {"max_results": 8},
    "get_sector_summary": {"sector": "电力设备"},
    "get_narrative_sector_summary": {"sector": "电力设备"},
    "get_fundamentals": {"stock_code": "SHM-000360"},
    "get_business_segments": {"stock_code": "SHM-000360"},
    "get_valuation": {"stock_code": "SHM-000360"},
    "get_announcements": {"stock_code": "SHM-000360", "days": 30},
    "get_announcement_evidence": {"stock_code": "SHM-000360", "days": 30},
    "get_news": {"days": 3, "keyword": "回购"},
    "get_narrative_news": {"days": 3, "market_relevant_only": True, "max_results": 15},
    "get_portfolio": {},
    "get_position": {"stock_code": "SHM-000360"},
    "place_order": {
        "action": "sell",
        "stock_code": "SHM-000360",
        "quantity": 0,
        "reasoning": "主题逻辑失效且价格跌破结构位，全部退出",
    },
    "manage_conditional_order": {
        "operation": "create",
        "action": "sell",
        "stock_code": "SHM-000360",
        "quantity": 0,
        "comparator": "price_lte",
        "trigger_price": 27.5,
        "protective": True,
        "reasoning": "跌破结构位时全部退出",
    },
    "list_conditional_orders": {"status": "active"},
    "add_watchlist": {"stock_code": "SHM-000360", "reason": "等待板块扩散确认"},
    "remove_watchlist": {"stock_code": "SHM-000360"},
    "get_watchlist": {},
    "remember": {
        "content": "板块扩散连续两日下降时，不再把单股冲高视为主线延续。",
        "memory_type": "lesson",
        "tags": ["板块扩散", "退出"],
        "importance": 0.7,
    },
    "search_memory": {"query": "板块扩散 退出", "memory_type": "lesson", "max_results": 5},
    "get_memory": {"memory_id": "mem-0012"},
    "execute_code": {
        "code": (
            "from traderharness_api import market\n"
            "features = market.get_behavioral_features()\n"
            "result = features.sort_values('change_20_pct', ascending=False)"
            ".head(5).to_dict('records')"
        )
    },
    "complete_phase": {
        "decision": "monitor",
        "summary": "已完成候选核验，当前证据不足，不交易。",
        "next_focus": "观察板块扩散和候选承接是否增强。",
    },
    "finish_day": {"summary": "今日未交易；主线扩散不足，保留现金等待确认。"},
}

TOOL_RESULT_SUMMARIES: dict[str, str] = {
    "get_kline": "stock_code、count、recent_20，以及请求超过20日时的 older_summary。",
    "get_stock_price": "stock_code、price/close、change_pct、price_source 和 as_of。",
    "get_stock_info": "stock_code、name、industry、market。",
    "get_market_overview": "涨跌家数、领涨/领跌板块和板块总数。",
    "get_narrative_market_overview": "多周期板块强度、扩散和高低切候选。",
    "screen_stocks": "stocks 候选数组、total_matched 和实际返回数。",
    "screen_behavioral_cycle": "行为量价候选、样本规模、匹配规模和点时规则。",
    "get_sector_summary": "板块平均涨跌、成分数量和领涨/领跌候选。",
    "get_narrative_sector_summary": "板块多周期强度、扩散和龙头比较证据。",
    "get_fundamentals": "已公开最新财务指标；比率字段单位为百分比。",
    "get_business_segments": "主营分部、收入占比、毛利率和亿元人民币收入。",
    "get_valuation": "PE/PB/PS、换手率、ST状态和数据日期。",
    "get_announcements": "公告标题、点时时间、类型和匹配总数。",
    "get_announcement_evidence": "带 evidence_id 的公告标题、点时时间和类型。",
    "get_news": "快讯标题、内容、点时时间、等级和匹配总数。",
    "get_narrative_news": "带 evidence_id 的文本证据、标签、关联股票和匹配总数。",
    "get_portfolio": "现金、总资产、收益率、估值来源和全部持仓。",
    "get_position": "数量、成本、当前标记价、可卖数量、盈亏和持仓计划。",
    "place_order": "成交动作、代码、价格、数量、现金和成交后组合。",
    "manage_conditional_order": "创建/修改/取消后的完整条件单状态。",
    "list_conditional_orders": "匹配状态的条件单、版本和失败尝试。",
    "add_watchlist": "加入结果、关注理由、有效期和自选总数。",
    "remove_watchlist": "移除结果和被移除代码。",
    "get_watchlist": "自选代码、原因、有效期、标记价格及价格来源。",
    "remember": "新记忆及 memory_id、版本链和状态。",
    "search_memory": "确定性检索命中的记忆数组和数量。",
    "get_memory": "指定 memory_id 的完整记录和版本状态。",
    "execute_code": "stdout、result，以及失败时的 traceback 和定位信息。",
    "complete_phase": "阶段、子窗口、显式结论、摘要和下一步关注点。",
    "finish_day": "日终状态、已保存摘要和当日成交数。",
}

TOOL_NOTES: dict[str, str] = {
    "get_kline": "只返回严格早于当前交易日的日K；当日5分钟数据由窗口消息或沙箱 get_kline_5min 提供。",
    "get_stock_price": "盘前返回D-1日线；盘中返回当前已揭示子窗口的最新5分钟收盘价，并标明来源。",
    "get_narrative_sector_summary": "每个交易日最多查询两个不同板块；预算耗尽不可重试。",
    "get_fundamentals": "roe、net_profit_margin、gross_margin 和同比字段统一以百分比返回。",
    "get_business_segments": "revenue_100m_cny 的单位是亿元人民币，不使用含糊的 billion 字段名。",
    "get_announcements": "成功结果同时包含标题和点时时间。",
    "get_narrative_news": "每个交易日最多执行两个不同查询；预算耗尽不可重试。",
    "get_portfolio": "盘前按D-1收盘估值，盘中优先使用当前已揭示窗口价格，并返回 price_source。",
    "manage_conditional_order": (
        "create、update、cancel 的必填字段不同；expires_in_trading_days 是从当前交易日起计算的相对有效期。"
    ),
    "remember": (
        "同类型且标签重合的活动结论必须用 supersedes_id 留痕替换；达到活动记忆上限时先 search_memory，"
        "再用返回的 memory_id 重试。"
    ),
    "execute_code": "代码失败时读取 error_code、correction 和 traceback，只修正同一分析目标后重试。",
    "finish_day": "summary 最多500个字符。",
}

NON_RETRYABLE_ERROR_CODES = frozenset(
    {
        "daily_memory_limit_reached",
        "daily_tool_budget_exhausted",
        "decision_card_semantic_rejection",
        "conditional_order_cannot_open_position",
        "environment_unavailable",
        "market_execution_blocked",
        "order_temporarily_ineligible",
        "order_unavailable_in_phase",
        "position_not_held",
        "sandbox_daily_limit_reached",
        "security_data_unavailable",
        "security_ineligible",
        "data_unavailable",
        "watchlist_entry_not_found",
    }
)

FIELD_DESCRIPTIONS: dict[str, str] = {
    "days": "向当前时间点回看多少天或交易日；省略时使用字段默认值。",
    "max_results": "最多返回多少条结果；省略时使用字段默认值。",
    "sector": "板块或行业名称，必须使用市场概览返回的可见名称。",
    "price_min": "最低收盘价（含边界），必须大于等于0。",
    "price_max": "最高收盘价（含边界），必须大于0且不小于 price_min。",
    "change_pct_min": "最小单日涨跌幅，单位为百分比。",
    "change_pct_max": "最大单日涨跌幅，单位为百分比。",
    "volume_min": "最小成交量，单位为股。",
    "industry": "行业名称子串；省略表示不过滤行业。",
    "sort_by": "候选排序字段。",
    "keyword": "按字面值匹配的关键词，不按正则表达式解释。",
    "market_relevant_only": "是否仅保留高等级或带市场标签、关联证券的快讯。",
    "action": "交易方向：buy 买入，sell 卖出。",
    "stock_name": "可选可见证券名称；省略时使用可见代码。",
    "quantity": "交易股数；买入为100的整数倍，卖出0表示全部可卖数量。",
    "reasoning": "可审计理由，包含证据、风险、失效条件和后续动作。",
    "behavior_hypothesis": "新建仓时的可证伪群体行为假设。",
    "confirmation_level": "新建仓确认价格，必须大于0。",
    "original_structural_stop": "冻结的原始结构止损价，必须大于0且低于多头成交价。",
    "exit_condition": "可机械核验的退出或失效条件。",
    "expected_holding_days": "预期持有交易日数，必须为正整数。",
    "decision_card": "要求决策卡的 Agent 新建买仓时必填的语义裁决对象。",
    "status": "状态过滤器。",
    "reason": "加入自选的可观察理由；省略表示不记录理由。",
    "content": "简洁、可验证、可跨日复用的记忆内容。",
    "memory_type": "记忆类型；必须使用枚举值。",
    "tags": "用于检索和冲突判断的短标签数组。",
    "importance": "重要度，0到1；省略时为0.5。",
    "query": "确定性词法检索关键词；使用与记忆标签或内容一致的词。",
    "memory_id": "从 remember、search_memory 或候选纠错信息原样复制的记忆ID。",
    "code": "完整可执行 Python 源码；将最终值赋给 result，或使用 print 输出。",
    "summary": "本阶段或本交易日的可审计摘要。",
    "next_focus": "下一阶段需要验证的价格、资金或失效条件。",
    "abandon_error_codes": (
        "若明确放弃某个失败动作，列出仍处于待纠错状态的 error_code；"
        "同时必须在 summary 中说明放弃原因。省略表示没有放弃。"
    ),
}

DECISION_CARD_FIELD_DESCRIPTIONS: dict[str, str] = {
    "decision": "语义结论；只有 trade 可以提交新建仓订单。",
    "mode": "leader_attack 龙头进攻或 high_low_rotation 高低切重新定价。",
    "entry_setup": "低位启动、趋势持续确认或龙头健康回踩。",
    "theme": "市场正在交易的主题名称。",
    "theme_logic": "催化如何传导到收入、利润或风险偏好的因果链。",
    "text_evidence_ids": "精确复制文本工具返回的 evidence_id，至少一项。",
    "business_fit": "公司主营与主题直接、间接或概念关联的判断。",
    "business_fit_basis": "主营契合判断所用的证据类型。",
    "sector_state": "板块当前的领先、重新定价、单股脉冲或不明确状态。",
    "sector_confirmation": "板块扩散和资金确认依据，不能只描述单只股票。",
    "candidate_role": "候选在当前主题中的市场角色。",
    "leadership_comparison": "与同板块更强候选的启动、抗跌、修复和流动性比较。",
    "best_expression_reason": "为什么它是当前主题和模式的最优可交易表达。",
    "candidate_rank": "最优表达、较弱备选或无法确认。",
    "stronger_candidate_status": "是否识别出更强候选，以及该候选是否可交易。",
    "execution_compromise": "是否因成交便利而降级选择较弱候选。",
    "capacity_liquidity": "成交容量、换手和计划仓位承接依据。",
    "price_volume_confirmation": "当前已可见量价对主题和地位判断的确认。",
    "market_stage": "启动、确认、回踩、加速、高潮、派发或重新定价阶段。",
    "extension_assessment": "延伸程度及跳空、承接和失效位是否可管理。",
    "counter_evidence": "当前最强反证和它将如何推翻交易结论。",
    "why_now": "为什么当前子窗口满足入场，而不是继续等待。",
    "abstention_case": "什么证据会使本次选择放弃。",
    "invalidation": "主题、板块、地位或价格结构的明确失效条件。",
}


def is_current_contract(version: str | None) -> bool:
    return version == CURRENT_TOOL_CONTRACT_VERSION


def tool_example(name: str) -> dict[str, Any] | None:
    example = TOOL_EXAMPLES.get(name)
    return copy.deepcopy(example) if example is not None else None


def build_current_description(name: str, legacy_description: str) -> str:
    """Build a compact model-visible contract without changing legacy text."""
    sections = [legacy_description.strip()]
    note = TOOL_NOTES.get(name)
    if note:
        sections.append(note)
    example = TOOL_EXAMPLES.get(name)
    if example is not None:
        sections.append(
            "正确调用示例（仅 arguments）：" + json.dumps(example, ensure_ascii=False, separators=(",", ":"))
        )
    summary = TOOL_RESULT_SUMMARIES.get(name)
    if summary:
        sections.append("成功返回：success=true；" + summary)
    sections.append(
        "失败统一返回 success=false、error、error_code、retryable 和 correction；retryable=false 时不要重复调用。"
    )
    return "\n".join(section for section in sections if section)


def _set_description(prop: dict, text: str) -> None:
    prop["description"] = text


def build_current_parameters(name: str, legacy_parameters: dict, ctx: Any = None) -> dict:
    """Return the strict v5 input schema for one tool."""
    schema = copy.deepcopy(legacy_parameters or {})
    schema.setdefault("type", "object")
    properties = schema.setdefault("properties", {})
    schema.setdefault("required", [])
    schema["additionalProperties"] = False

    stock_code = properties.get("stock_code")
    if isinstance(stock_code, dict):
        stock_code["type"] = "string"
        stock_code["minLength"] = 6
        _set_description(stock_code, STOCK_CODE_DESCRIPTION)

    for field in schema.get("required", []):
        prop = properties.get(field)
        if isinstance(prop, dict) and prop.get("type") == "string":
            prop.setdefault("minLength", 1)

    if "days" in properties:
        properties["days"].setdefault("minimum", 1)
        maximum = 3 if name in {"get_news", "get_narrative_news"} else 90
        if name == "get_kline":
            maximum = 120
        properties["days"].setdefault("maximum", maximum)
        properties["days"].setdefault(
            "default",
            20 if name == "get_kline" else 30 if "announcement" in name else 3,
        )

    if "max_results" in properties:
        properties["max_results"].setdefault("minimum", 1)
        properties["max_results"].setdefault(
            "maximum", 20 if name in {"screen_behavioral_cycle", "search_memory"} else 30
        )
        properties["max_results"].setdefault(
            "default",
            8
            if name == "screen_behavioral_cycle"
            else 5
            if name == "search_memory"
            else 15
            if name == "get_narrative_news"
            else 10,
        )

    if name == "screen_stocks":
        properties["price_min"].setdefault("minimum", 0)
        properties["price_max"].setdefault("exclusiveMinimum", 0)
        properties["volume_min"].setdefault("minimum", 0)
        properties["max_results"]["minimum"] = 1
        properties["max_results"]["maximum"] = 30
    elif name == "search_memory":
        properties["memory_type"]["enum"] = [
            "lesson",
            "hypothesis",
            "position_plan",
            "risk_rule",
            "observation",
        ]
        properties["max_results"].setdefault("default", 5)
    elif name == "remember":
        properties["content"].setdefault("maxLength", 2000)
        properties["tags"].setdefault("maxItems", 20)
        properties["tags"].setdefault("default", [])
        properties["importance"].setdefault("default", 0.5)
        properties["supersedes_id"]["description"] = (
            "被本记录替代的活动 memory_id。同类型同标签已存在或活动记忆达到上限时必须填写；"
            "先用 search_memory 获取准确 ID。"
        )
    elif name == "finish_day":
        properties["summary"]["maxLength"] = 500
        properties["abandon_error_codes"] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "maxItems": 20,
            "default": [],
        }
    elif name == "complete_phase":
        properties["summary"].setdefault("maxLength", 1000)
        properties["next_focus"].setdefault("maxLength", 1000)
        properties["abandon_error_codes"] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "maxItems": 20,
            "default": [],
        }
    elif name == "execute_code":
        properties["code"].setdefault("minLength", 1)
        properties["code"].setdefault("maxLength", 20000)
    elif name == "place_order":
        properties["quantity"]["minimum"] = 0
        properties["reasoning"].setdefault("minLength", 1)
        properties["expected_holding_days"].setdefault("minimum", 1)
        properties["confirmation_level"].setdefault("exclusiveMinimum", 0)
        properties["original_structural_stop"].setdefault("exclusiveMinimum", 0)
        schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"action": {"const": "buy"}},
                    "required": ["action"],
                },
                "then": {
                    "properties": {
                        "quantity": {"minimum": 100, "multipleOf": 100},
                    }
                },
            }
        )
        if getattr(ctx, "require_structured_plan", False):
            schema["allOf"].append(
                {
                    "if": {
                        "properties": {"action": {"const": "buy"}},
                        "required": ["action"],
                    },
                    "then": {
                        "required": [
                            "behavior_hypothesis",
                            "confirmation_level",
                            "original_structural_stop",
                            "exit_condition",
                            "expected_holding_days",
                        ]
                    },
                }
            )
        if getattr(ctx, "require_decision_card", False):
            schema["allOf"].append(
                {
                    "if": {
                        "properties": {"action": {"const": "buy"}},
                        "required": ["action"],
                    },
                    "then": {"required": ["decision_card"]},
                }
            )
    elif name == "manage_conditional_order":
        properties.pop("expires_day_index", None)
        properties["expires_in_trading_days"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": 250,
            "description": "从当前交易日起计算的有效交易日数；省略表示不过期。",
        }
        properties["operation"]["description"] = "create、update 或 cancel。"
        properties["order_id"]["description"] = "update/cancel 必填；从 list_conditional_orders 原样复制。"
        properties["action"]["description"] = "create 必填；条件触发后执行 buy 或 sell。"
        properties["comparator"]["description"] = (
            "create 必填；price_lte 表示价格小于等于触发，price_gte 表示大于等于触发。"
        )
        properties["trigger_price"].update(
            {"exclusiveMinimum": 0, "description": "create 必填；update 时可用于修改触发价。"}
        )
        properties["quantity"].update(
            {"minimum": 0, "description": "create 必填；买入须为正整数手，卖出时0表示全部可卖。"}
        )
        properties["protective"]["description"] = "仅 sell 且 quantity=0 可设为 true；保护止损只能上移。"
        properties["reasoning"].update({"minLength": 1, "maxLength": 2000})
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"operation": {"const": "create"}},
                    "required": ["operation"],
                },
                "then": {
                    "required": [
                        "action",
                        "stock_code",
                        "quantity",
                        "comparator",
                        "trigger_price",
                    ]
                },
            },
            {
                "if": {
                    "properties": {"operation": {"const": "update"}},
                    "required": ["operation"],
                },
                "then": {
                    "required": ["order_id"],
                    "anyOf": [{"required": ["trigger_price"]}, {"required": ["quantity"]}],
                },
            },
            {
                "if": {
                    "properties": {"operation": {"const": "cancel"}},
                    "required": ["operation"],
                },
                "then": {"required": ["order_id"]},
            },
            {
                "if": {
                    "properties": {
                        "operation": {"const": "create"},
                        "action": {"const": "buy"},
                    },
                    "required": ["operation", "action"],
                },
                "then": {
                    "properties": {
                        "quantity": {"minimum": 100, "multipleOf": 100},
                    }
                },
            },
            {
                "if": {
                    "properties": {"protective": {"const": True}},
                    "required": ["protective"],
                },
                "then": {
                    "properties": {
                        "action": {"const": "sell"},
                        "quantity": {"const": 0},
                        "comparator": {"const": "price_lte"},
                    },
                    "required": ["action", "quantity", "comparator"],
                },
            },
        ]
    elif name == "list_conditional_orders":
        schema.setdefault("required", [])
        properties["status"].setdefault("default", "active")
        properties["status"]["description"] = "按状态过滤；默认 active，all 返回全部状态。"

    for field, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        prop.setdefault("description", FIELD_DESCRIPTIONS.get(field, f"参数 {field}。"))
        if field == "decision_card":
            for card_field, card_prop in prop.get("properties", {}).items():
                if isinstance(card_prop, dict):
                    card_prop.setdefault(
                        "description",
                        DECISION_CARD_FIELD_DESCRIPTIONS.get(
                            card_field,
                            f"决策卡字段 {card_field}。",
                        ),
                    )

    return schema


def output_schema_for(name: str) -> dict:
    """Machine-readable common result envelope plus tool-specific payload summary."""
    return {
        "oneOf": [
            {
                "type": "object",
                "required": ["success"],
                "properties": {
                    "success": {"const": True},
                },
                "additionalProperties": True,
                "description": TOOL_RESULT_SUMMARIES.get(name, "工具成功结果。"),
            },
            {
                "type": "object",
                "required": ["success", "error", "error_code", "retryable", "correction"],
                "properties": {
                    "success": {"const": False},
                    "error": {"type": "string"},
                    "error_code": {"type": "string"},
                    "retryable": {"type": "boolean"},
                    "correction": {"type": "object"},
                },
                "additionalProperties": True,
            },
        ]
    }


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_instance(value: Any, schema: dict, path: str = "$") -> list[dict[str, str]]:
    """Validate the JSON-Schema subset used by Agent tools.

    Returning all deterministic issues is more useful to an LLM than raising
    on the first one, and avoids adding a heavyweight runtime dependency.
    """
    issues: list[dict[str, str]] = []

    if "const" in schema and value != schema["const"]:
        issues.append({"path": path, "message": f"必须等于 {schema['const']!r}"})
        return issues
    if "enum" in schema and value not in schema["enum"]:
        issues.append({"path": path, "message": f"必须是 {schema['enum']} 之一"})

    expected_type = schema.get("type")
    if expected_type and not _type_matches(value, expected_type):
        issues.append(
            {
                "path": path,
                "message": f"类型必须是 {expected_type}，实际是 {type(value).__name__}",
            }
        )
        return issues

    if isinstance(value, dict):
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                issues.append({"path": path, "message": f"缺少必填字段 {field}"})
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    issues.append({"path": f"{path}.{field}", "message": "不允许的字段"})
        for field, item in value.items():
            child_schema = properties.get(field)
            if isinstance(child_schema, dict):
                issues.extend(validate_instance(item, child_schema, f"{path}.{field}"))

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            issues.append({"path": path, "message": f"至少需要 {schema['minItems']} 项"})
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            issues.append({"path": path, "message": f"最多允许 {schema['maxItems']} 项"})
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(validate_instance(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            issues.append({"path": path, "message": f"长度至少为 {schema['minLength']}"})
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            issues.append({"path": path, "message": f"长度最多为 {schema['maxLength']}"})

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            issues.append({"path": path, "message": "必须是有限数值"})
        if "minimum" in schema and number < float(schema["minimum"]):
            issues.append({"path": path, "message": f"必须大于等于 {schema['minimum']}"})
        if "maximum" in schema and number > float(schema["maximum"]):
            issues.append({"path": path, "message": f"必须小于等于 {schema['maximum']}"})
        if "exclusiveMinimum" in schema and number <= float(schema["exclusiveMinimum"]):
            issues.append({"path": path, "message": f"必须大于 {schema['exclusiveMinimum']}"})
        multiple = schema.get("multipleOf")
        if multiple and not math.isclose(number % float(multiple), 0.0, abs_tol=1e-9):
            issues.append({"path": path, "message": f"必须是 {multiple} 的整数倍"})

    for child in schema.get("allOf", []):
        issues.extend(validate_instance(value, child, path))

    if "if" in schema:
        condition_matches = not validate_instance(value, schema["if"], path)
        branch = schema.get("then") if condition_matches else schema.get("else")
        if isinstance(branch, dict):
            issues.extend(validate_instance(value, branch, path))

    if "anyOf" in schema:
        branches = [validate_instance(value, child, path) for child in schema["anyOf"]]
        if not any(not branch for branch in branches):
            issues.append({"path": path, "message": "必须满足 anyOf 中至少一个字段组合"})

    if "oneOf" in schema:
        branches = [validate_instance(value, child, path) for child in schema["oneOf"]]
        if sum(not branch for branch in branches) != 1:
            issues.append({"path": path, "message": "必须且只能满足 oneOf 中一个字段组合"})

    return issues
