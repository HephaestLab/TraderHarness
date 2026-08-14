"""Structured position-plan enforcement for behavior agents."""

from datetime import date
from decimal import Decimal

import pytest

from traderharness.core.portfolio import Portfolio
from traderharness.tools.portfolio import handle_get_position
from traderharness.tools.registry import ToolContext
from traderharness.tools.trading import handle_place_order


class _Bus:
    def __init__(self, portfolio: Portfolio, price: str = "10.00") -> None:
        self.portfolio = portfolio
        self.price = Decimal(price)
        self.calls = 0
        self.conditional_orders = []
        self.current_date = date(2024, 3, 1)

    def get_execution_price(self, code: str, window: str = "open") -> Decimal:
        return self.price

    def place_order(
        self,
        *,
        agent_id: str,
        stock_code: str,
        side: str,
        quantity: int,
        stock_name: str,
        reasoning: str,
        window: str,
    ) -> dict:
        self.calls += 1
        if side == "buy":
            trade = self.portfolio.buy(
                stock_code, stock_name, self.price, quantity, self.current_date
            )
        else:
            pos = self.portfolio.positions[stock_code]
            sellable = pos.sellable_quantity(self.current_date)
            sold = sellable if quantity == 0 else min(quantity, sellable)
            avg_cost = pos.avg_cost
            trade = self.portfolio.sell(stock_code, self.price, sold, self.current_date)
            trade["pnl"] = float(trade["net_income"]) - float(avg_cost * sold)
        return {"success": True, "trade": trade}

    def create_conditional_order(self, **kwargs) -> dict:
        order = {"order_id": f"cond-{len(self.conditional_orders) + 1:04d}", **kwargs}
        self.conditional_orders.append(order)
        return order


def _ctx(
    *, price: str = "10.00", day_index: int = 10, minimum_holding_days: int = 5
) -> tuple[ToolContext, _Bus]:
    portfolio = Portfolio(Decimal("1000000"))
    bus = _Bus(portfolio, price)
    ctx = ToolContext(
        current_date=date(2024, 3, 1),
        current_phase="open_window",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        execution_price={"600519": Decimal(price)},
        close_prices={"600519": Decimal(price)},
        agent_id="behavioral-cycle",
        require_structured_plan=True,
        minimum_holding_days=minimum_holding_days,
        day_index=day_index,
        max_position_pct=100.0,
        _bus=bus,
    )
    ctx.tool_call_cache["_position_plans"] = {}
    ctx.tool_call_cache["_agent_tool_results"] = {
        "get_stock_info": {
            "600519": {"stock_code": "600519", "industry": "power"}
        },
        "get_business_segments": {
            "600519": {
                "stock_code": "600519",
                "segments": [{"name": "data-center power", "revenue_pct": "60.0%"}],
            }
        },
        "get_valuation": {"600519": {"stock_code": "600519", "pe_ttm": 20.0}},
        "get_kline": {"600519": {"stock_code": "600519", "recent_20": []}},
        "get_stock_price": {
            "600519": {"stock_code": "600519", "close": float(price)}
        },
    }
    return ctx, bus


def _buy_args() -> dict:
    return {
        "action": "buy",
        "stock_code": "600519",
        "stock_name": "company",
        "quantity": 30_000,
        "reasoning": "confirmed crowd pressure",
        "behavior_hypothesis": "attention shock followed by confirmed demand",
        "confirmation_level": 9.80,
        "original_structural_stop": 9.40,
        "exit_condition": "price reaches the original structural stop",
        "expected_holding_days": 15,
    }


def _decision_card(**overrides) -> dict:
    card = {
        "decision": "trade",
        "mode": "leader_attack",
        "entry_setup": "leader_pullback",
        "theme": "算力电力协同",
        "theme_logic": "电力约束提高数据中心绿电需求，盈利改善路径可追踪。",
        "text_evidence_ids": ["news:101", "announcement:600519:7"],
        "business_fit_basis": "direct_segments",
        "business_fit": "主营收入直接来自主题核心环节，不是关键词关联。",
        "sector_state": "confirmed_leading",
        "sector_confirmation": "板块强度、扩散与持续性共同确认，不是单股脉冲。",
        "candidate_role": "true_leader",
        "leadership_comparison": "与同主题最强三只股票比较后，辨识度和承接更强。",
        "best_expression_reason": "主题辨识度、业务契合与交易承接均为同方向最强。",
        "candidate_rank": "best_expression",
        "stronger_candidate_status": "none_identified",
        "execution_compromise": "none",
        "capacity_liquidity": "成交额与换手可承接目标仓位，分时流动性稳定。",
        "price_volume_confirmation": "分歧后缩量守住结构位，回升时量能恢复。",
        "market_stage": "healthy_pullback",
        "extension_assessment": "acceptable",
        "counter_evidence": "板块扩散可能衰减，催化也可能已被部分定价。",
        "why_now": "首次健康回踩确认，当前赔率优于追逐加速段。",
        "abstention_case": "若真龙头继续加速且本股只是补涨，应完全放弃该主题。",
        "invalidation": "收盘跌破结构位且板块扩散连续走弱。",
    }
    card.update(overrides)
    return card


@pytest.mark.asyncio
async def test_semantic_agent_requires_complete_decision_card_without_quantizing_leadership():
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card()

    result = await handle_place_order(args, ctx)

    assert result["success"] is True
    frozen = ctx.tool_call_cache["_position_plans"]["600519"]["decision_card"]
    assert frozen["theme_logic"].startswith("电力约束")
    assert "change_20_pct" not in frozen
    assert bus.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"business_fit": ""}, "business_fit"),
        ({"candidate_role": "follower"}, "candidate_role"),
        ({"sector_state": "single_stock_only"}, "sector_state"),
        ({"extension_assessment": "overextended"}, "overextended"),
        ({"candidate_rank": "weaker_alternative"}, "candidate_rank"),
        ({"stronger_candidate_status": "unavailable"}, "stronger_candidate_status"),
        ({"execution_compromise": "weaker_substitute"}, "execution_compromise"),
        ({"decision": "abstain"}, "abstain"),
    ],
)
async def test_semantic_card_rejects_its_own_incomplete_or_no_trade_conclusion(
    overrides, expected
):
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card(**overrides)

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert expected in result["error"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_rotation_mode_accepts_llm_assessed_rotation_core_role():
    ctx, _ = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card(
        mode="high_low_rotation",
        entry_setup="low_base_ignition",
        candidate_role="rotation_core",
        sector_state="confirmed_repricing",
        market_stage="repricing",
    )

    result = await handle_place_order(args, ctx)

    assert result["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entry_setup", "candidate_role", "sector_state", "extension"),
    [
        ("low_base_ignition", "emerging_leader", "emerging_leading", "acceptable"),
        ("trend_continuation", "true_leader", "confirmed_leading", "managed_extension"),
        ("leader_pullback", "true_leader", "confirmed_leading", "acceptable"),
    ],
)
async def test_leader_attack_accepts_all_three_semantic_entry_paths(
    entry_setup, candidate_role, sector_state, extension
):
    ctx, _ = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card(
        entry_setup=entry_setup,
        candidate_role=candidate_role,
        sector_state=sector_state,
        extension_assessment=extension,
    )

    result = await handle_place_order(args, ctx)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_semantic_card_rejects_misnested_plan_fields_and_unseen_evidence_ids():
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card(confirmation_level="10.0")

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert "confirmation_level" in result["error"]
    assert result["error_code"] == "decision_card_unknown_fields"
    assert result["retryable"] is True
    assert result["retry_kind"] == "decision_card_correction"
    assert "confirmation_level" in result["correction"]["invalid_fields"]
    assert bus.calls == 0

    args["decision_card"] = _decision_card()
    ctx.tool_call_cache["_visible_text_evidence_ids"] = {"news:101"}

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert "announcement:600519:7" in result["error"]
    assert result["error_code"] == "decision_card_unseen_evidence"
    assert result["retryable"] is True
    assert result["correction"]["available_evidence_ids"] == ["news:101"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_semantic_no_trade_conclusion_is_explicitly_not_retryable():
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    args = _buy_args()
    args["decision_card"] = _decision_card(candidate_rank="weaker_alternative")

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert result["error_code"] == "decision_card_semantic_rejection"
    assert result["retryable"] is False
    assert result["correction"]["instruction"].startswith("保持原语义结论")
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_semantic_buy_requires_successful_candidate_tool_evidence():
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    del ctx.tool_call_cache["_agent_tool_results"]["get_valuation"]["600519"]
    args = _buy_args()
    args["decision_card"] = _decision_card()

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert result["error_code"] == "decision_card_missing_tool_evidence"
    assert result["correction"]["missing_tools"] == ["get_valuation"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_direct_business_fit_cannot_be_claimed_from_blank_segments():
    ctx, bus = _ctx()
    ctx.require_decision_card = True
    ctx.tool_call_cache["_agent_tool_results"]["get_business_segments"]["600519"] = {
        "stock_code": "600519",
        "segments": [{"name": "", "revenue_pct": None}],
    }
    args = _buy_args()
    args["decision_card"] = _decision_card(business_fit_basis="direct_segments")

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert result["error_code"] == "decision_card_ungrounded_business_fit"
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_semantic_buy_waits_until_confirmation_level_is_reached():
    ctx, bus = _ctx(price="10.00")
    ctx.require_decision_card = True
    args = _buy_args()
    args["confirmation_level"] = "10.10"
    args["decision_card"] = _decision_card()

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert result["error_code"] == "decision_card_semantic_rejection"
    assert "confirmation_level" in result["error"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_missing_top_level_plan_fields_return_clear_repair_instructions():
    ctx, bus = _ctx()
    args = _buy_args()
    del args["confirmation_level"]
    del args["expected_holding_days"]

    result = await handle_place_order(args, ctx)

    assert result["success"] is False
    assert result["error_code"] == "structured_plan_missing_fields"
    assert result["retryable"] is True
    assert result["correction"]["place_at_order_top_level"] == [
        "confirmation_level",
        "expected_holding_days",
    ]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_structured_agent_rejects_buy_without_frozen_plan():
    ctx, bus = _ctx()

    result = await handle_place_order(
        {
            "action": "buy",
            "stock_code": "600519",
            "quantity": 30_000,
            "reasoning": "missing plan",
        },
        ctx,
    )

    assert result["success"] is False
    assert "结构化" in result["error"]
    assert bus.calls == 0


@pytest.mark.asyncio
async def test_buy_freezes_plan_and_position_reports_trading_days():
    ctx, bus = _ctx()
    result = await handle_place_order(_buy_args(), ctx)
    assert result["success"] is True

    plan = ctx.tool_call_cache["_position_plans"]["600519"]
    assert plan["original_structural_stop"] == 9.4
    assert plan["entry_day_index"] == 10
    assert plan["minimum_holding_days"] == 5
    assert plan["conditional_order_id"] == "cond-0001"
    assert bus.conditional_orders[0]["comparator"] == "price_lte"
    assert bus.conditional_orders[0]["trigger_price"] == Decimal("9.4")
    assert bus.conditional_orders[0]["not_before_day_index"] == 11

    ctx.day_index = 12
    ctx.current_date = date(2024, 3, 5)
    position = await handle_get_position({"stock_code": "600519"}, ctx)
    assert position["holding_trading_days"] == 2
    assert position["position_plan"]["original_structural_stop"] == 9.4


@pytest.mark.asyncio
async def test_early_sell_above_original_stop_is_rejected():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 4)
    bus.price = Decimal("9.60")
    ctx.current_date = bus.current_date
    ctx.day_index = 11
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    result = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "long upper shadow therefore distribution",
        },
        ctx,
    )

    assert result["success"] is False
    assert "最短持有" in result["error"]
    assert result["position_plan"]["original_structural_stop"] == 9.4
    assert ctx.portfolio.positions["600519"].quantity == 30_000
    assert bus.calls == 1


@pytest.mark.asyncio
async def test_early_hard_stop_requires_full_exit_and_removes_plan():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 4)
    bus.price = Decimal("9.35")
    ctx.current_date = bus.current_date
    ctx.day_index = 11
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    partial = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 10_000,
            "reasoning": "hard stop",
        },
        ctx,
    )
    assert partial["success"] is False
    assert "全部" in partial["error"]

    full = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "hard stop",
        },
        ctx,
    )
    assert full["success"] is True
    assert "600519" not in ctx.portfolio.positions
    assert "600519" not in ctx.tool_call_cache["_position_plans"]


@pytest.mark.asyncio
async def test_sell_after_minimum_holding_period_is_allowed_above_stop():
    ctx, bus = _ctx()
    await handle_place_order(_buy_args(), ctx)
    bus.current_date = date(2024, 3, 8)
    bus.price = Decimal("10.50")
    ctx.current_date = bus.current_date
    ctx.day_index = 15
    ctx.execution_price["600519"] = bus.price
    ctx.traded_today.clear()

    result = await handle_place_order(
        {
            "action": "sell",
            "stock_code": "600519",
            "quantity": 0,
            "reasoning": "planned exit after minimum hold",
        },
        ctx,
    )

    assert result["success"] is True
