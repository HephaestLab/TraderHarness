"""Contract tests for the behavioral-cycle builtin trading agent."""

from traderharness.agents.agent_card import BUILTIN_STORAGE_DIR, load_card
from traderharness.tools.catalog import CORE_TOOL_NAMES


def test_behavioral_cycle_card_freezes_the_research_contract():
    card = load_card("behavioral-cycle", BUILTIN_STORAGE_DIR)

    assert card is not None
    assert card.model == "deepseek-v4-flash"
    assert card.holding_period == "10-40 trading days"
    assert card.max_positions == 4
    assert card.max_position_pct == 100.0
    assert card.max_pre_iterations == 5
    assert card.max_window_iterations == 1
    assert card.require_structured_plan is True
    assert card.minimum_holding_days == 5
    assert card.research_interval_days == 5
    assert card.sandbox_pre_market_only is True
    assert card.sandbox_max_calls_per_day == 2
    assert CORE_TOOL_NAMES <= set(card.allowed_tools)
    assert "execute_code" in card.allowed_tools
    assert "screen_behavioral_cycle" not in card.allowed_tools

    # The strategy must express falsifiable price/volume hypotheses, not
    # attribute an unknowable intention to a supposed market operator.
    for required in (
        "群体行为压力",
        "不推断参与者身份",
        "execute_code",
        "get_behavioral_features",
        "risk_off / neutral / risk_on",
        "不设固定的单股仓位上限",
        "每只新股票首次建仓通常25%至40%",
        "上涨比例低于35%时视为risk_off，禁止新增风险",
        "risk_on且两个强确认机会",
        "90%至100%",
        "研究日：是",
        "同一份缓存快照",
        "add_watchlist",
        "开盘和尾盘阶段禁止 execute_code",
        "extended_20d",
        "禁止把 change_20_pct 或绝对涨幅设为正向得分",
        "注意力冲击",
        "价格反应",
        "完整确认",
        "已经完整收盘的交易日",
        "10个交易日冷却期",
        "至少5个交易日",
        "original_structural_stop",
        "minimum_holding_days",
        "不得重新解释阶段",
        "反证",
        "失效条件",
        "不得向下摊平成本",
    ):
        assert required in card.persona


def test_behavioral_cycle_card_has_only_documented_tools():
    card = load_card("behavioral-cycle", BUILTIN_STORAGE_DIR)
    assert card is not None

    expected_tools = {
        "get_kline",
        "get_stock_price",
        "get_stock_info",
        "get_market_overview",
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
        "finish_day",
    }
    assert set(card.allowed_tools) == expected_tools
