"""Contract tests for the behavioral-cycle builtin trading agent."""

from traderharness.agents.agent_card import BUILTIN_STORAGE_DIR, load_card
from traderharness.tools.catalog import CORE_TOOL_NAMES


def test_behavioral_cycle_card_freezes_the_research_contract():
    card = load_card("behavioral-cycle", BUILTIN_STORAGE_DIR)

    assert card is not None
    assert card.model == "deepseek-v4-pro"
    assert card.holding_period == "1-30 trading days"
    assert card.max_positions == 4
    assert card.max_position_pct == 100.0
    assert card.max_pre_iterations == 9
    assert card.max_window_iterations == 2
    assert card.require_structured_plan is True
    assert card.require_decision_card is True
    assert card.require_phase_completion is True
    assert card.minimum_holding_days == 0
    assert card.watchlist_ttl_days == 10
    assert card.max_active_memories == 24
    assert card.max_daily_memories == 2
    assert card.research_interval_days == 5
    assert card.sandbox_pre_market_only is True
    assert card.sandbox_max_calls_per_day == 2
    assert CORE_TOOL_NAMES <= set(card.allowed_tools)
    assert "execute_code" in card.allowed_tools
    assert "screen_behavioral_cycle" not in card.allowed_tools

    # Python exposes facts; the LLM owns the semantic market/leadership verdict.
    for required in (
        "Python只负责整理点时安全的事实",
        "市场为什么交易一个方向",
        "主题、板块、公司、交易阶段",
        "leader_attack",
        "high_low_rotation",
        "leaders 只是量价比较候选",
        "新增文本催化",
        "板块扩散",
        "execute_code",
        "get_behavioral_features",
        "get_narrative_news",
        "第五轮完成判断",
        "get_announcement_evidence",
        "get_narrative_sector_summary",
        "get_business_segments",
        "成交额、换手和分时流动性",
        "true_leader",
        "rotation_core",
        "sector_state",
        "sector_confirmation",
        "single_stock_only",
        "补涨、跟风",
        "low_base_ignition",
        "trend_continuation",
        "leader_pullback",
        "emerging_leader",
        "managed_extension",
        "单一涨幅阈值",
        "overextended",
        "decision_card",
        "business_fit",
        "business_fit_basis",
        "capacity_liquidity",
        "abstention_case",
        "不再用分号标签拼接",
        "跳空风险",
        "add_watchlist",
        "开盘与尾盘禁止 execute_code",
        "目标持有1至30个交易日",
        "original_structural_stop",
        "反证",
        "禁止向下摊平",
        "主营业务",
        "决策卡",
        "仓位不设固定单股或总股票硬上限",
        "最大仓位不是用来弥补证据不足",
        "主动调用 complete_phase",
        "最后收盘阶段调用一次 finish_day",
        "资金明确迁往更强方向时卖出",
    ):
        assert required in card.persona

    for obsolete in ("MODE=", "THEME=", "LEADER_EVIDENCE="):
        assert obsolete not in card.persona
    assert "至少5日内" not in card.persona


def test_behavioral_cycle_card_has_only_documented_tools():
    card = load_card("behavioral-cycle", BUILTIN_STORAGE_DIR)
    assert card is not None

    expected_tools = {
        "get_kline",
        "get_stock_price",
        "get_stock_info",
        "get_narrative_market_overview",
        "get_narrative_sector_summary",
        "get_announcement_evidence",
        "get_narrative_news",
        "get_business_segments",
        "get_valuation",
        "get_portfolio",
        "get_position",
        "place_order",
        "manage_conditional_order",
        "list_conditional_orders",
        "add_watchlist",
        "remove_watchlist",
        "get_watchlist",
        "remember",
        "search_memory",
        "get_memory",
        "execute_code",
        "complete_phase",
        "finish_day",
    }
    assert set(card.allowed_tools) == expected_tools
