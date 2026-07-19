from datetime import date
from decimal import Decimal

from traderharness.core.engine import EngineResult
from traderharness.run_results import build_result_document


def test_build_result_document_includes_metrics_behavior_and_benchmark():
    result = EngineResult(
        trading_days=2,
        start_date=date(2024, 3, 4),
        end_date=date(2024, 3, 5),
        agent_data={
            "agent": {
                "equity_curve": [
                    (date(2024, 3, 4), Decimal("1000000")),
                    (date(2024, 3, 5), Decimal("1010000")),
                ],
                "trades": [
                    {
                        "date": date(2024, 3, 4),
                        "action": "buy",
                        "stock_code": "600001",
                        "quantity": 100,
                        "price": 10,
                    }
                ],
                "trajectory": {
                    "steps": [
                        {
                            "date": "2024-03-04",
                            "type": "tool_call",
                            "data": {"name": "get_kline"},
                        }
                    ]
                },
            }
        },
    )
    benchmark = [
        (date(2024, 3, 4), Decimal("1000000")),
        (date(2024, 3, 5), Decimal("1005000")),
    ]

    document = build_result_document(
        result,
        initial_cash=Decimal("1000000"),
        config={"mask_entities": True},
        benchmark_curve=benchmark,
    )

    agent = document["agent_data"]["agent"]
    assert agent["metrics"]["total_return_pct"] == 1.0
    assert agent["metrics"]["total_trades"] == 1
    assert agent["behavior"]["total_buy_count"] == 1
    assert agent["vs_benchmark"]["benchmark_return_pct"] == 0.5
    assert document["benchmark"]["name"] == "CSI 300"
