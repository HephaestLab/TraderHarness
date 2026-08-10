"""Real-data acceptance check for deterministic conditional-order execution.

This script does not call an LLM or the network. It loads the canonical local
daily and five-minute datasets, executes a two-day protected position, and can
persist a normal result document for UI/E2E inspection.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal

from traderharness.agents.memory import DailyMemory
from traderharness.core.engine import EngineResult, MarketData, TradingBus
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.events import EventBus
from traderharness.core.market_profile import AShareProfile
from traderharness.core.portfolio import Portfolio
from traderharness.data.market_data_manager import MarketDataManager
from traderharness.data.stock_registry_loader import get_stock_registry
from traderharness.results import generate_result_filename, save_complete
from traderharness.run_results import build_result_document


def run(*, save_result: bool = False) -> str | None:
    code = "600519"
    entry_day = date(2026, 3, 2)
    trigger_day = date(2026, 3, 3)
    manager = MarketDataManager()
    daily = manager.load_daily_for_codes(
        [code], start_date=date(2026, 2, 27), end_date=trigger_day
    )
    minutes = manager.load_5min(start_date=entry_day, end_date=trigger_day)
    minutes = minutes[minutes["stock_code"] == code].reset_index(drop=True)
    if daily.empty or minutes.empty:
        raise RuntimeError("canonical real data is incomplete for the acceptance interval")

    market = MarketData()
    market._ingest_combined_df(daily, is_5min=False)
    market._ingest_combined_df(minutes, is_5min=True)
    portfolio = Portfolio(Decimal("1000000"))
    bus = TradingBus(market, AShareProfile(), portfolio, EventBus())

    bus._set_date(entry_day)
    bus._day_index = 0
    bought = bus.place_order(
        "conditional-order-acceptance",
        code,
        "buy",
        100,
        stock_name="贵州茅台",
        reasoning="real-data acceptance entry",
        window="open_1",
    )
    assert bought["success"], bought
    condition = bus.create_conditional_order(
        agent_id="conditional-order-acceptance",
        stock_code=code,
        side="sell",
        quantity=0,
        comparator="price_lte",
        trigger_price=Decimal("1425.00"),
        reasoning="real-data structural stop acceptance",
        created_phase="open_1",
        protective=True,
        not_before_day_index=1,
    )
    portfolio.record_equity(entry_day, {code: bus.get_execution_price(code, "close")})

    bus._set_date(trigger_day)
    bus._day_index = 1
    assert bus.process_conditional_orders("conditional-order-acceptance", "open_1") == []
    outcomes = bus.process_conditional_orders("conditional-order-acceptance", "open_2")
    assert len(outcomes) == 1 and outcomes[0]["success"], outcomes
    trade = outcomes[0]["trade"]
    assert Decimal(str(trade["price"])) == Decimal("1423.00"), trade
    assert trade["conditional_order_id"] == condition["order_id"]
    portfolio.record_equity(trigger_day, {})

    memory = DailyMemory("conditional-order-acceptance")
    memory.remember(
        entry_day,
        "A protective stop is environment state, not a reminder in prose.",
        memory_type="risk_rule",
        tags=[code, "conditional-order"],
        importance=1.0,
        source="acceptance",
    )
    memory.add(trigger_day, "Protective order triggered on the first qualifying 5-minute close.")

    result = EngineResult(
        trading_days=2,
        start_date=entry_day,
        end_date=trigger_day,
        agent_data={
            "conditional-order-acceptance": {
                "equity_curve": portfolio.equity_curve,
                "trades": bus.trade_history,
                "trajectory": {"days": [], "steps": []},
                "conditional_orders": bus.list_conditional_orders(status=None),
                "conditional_order_events": bus.conditional_order_events,
                "memory_events": memory.audit_events(),
            }
        },
    )
    print(
        "PASS real-data conditional order:",
        f"{code} trigger={condition['trigger_price']:.2f}",
        f"fill={float(trade['price']):.2f}",
        f"day_index={trade['execution_day_index']}",
        f"time={trade['execution_time']}",
    )
    if not save_result:
        return None
    masking_daily = manager.load_daily(
        start_date=entry_day - timedelta(days=180), end_date=trigger_day
    )
    masking_codes = sorted(
        {str(value).zfill(6) for value in masking_daily["stock_code"].dropna().unique()}
    )
    registry = get_stock_registry()
    entity_mask_seed = 20260810
    entity_masker = EntityMasker(
        masking_codes,
        names={code: registry.get(code, {}).get("name", code) for code in masking_codes},
        seed=entity_mask_seed,
    )
    document = build_result_document(
        result,
        initial_cash=Decimal("1000000"),
        config={
            "acceptance": "real-data-conditional-order",
            "mask_entities": True,
            "entity_mask_seed": entity_mask_seed,
            "start_date": str(entry_day),
            "end_date": str(trigger_day),
        },
        entity_masker=entity_masker,
    )
    path = save_complete(generate_result_filename(), document)
    print(path)
    return str(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-result", action="store_true")
    args = parser.parse_args()
    run(save_result=args.save_result)
