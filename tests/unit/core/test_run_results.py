from datetime import date
from decimal import Decimal

from traderharness.core.engine import EngineResult
from traderharness.core.entity_masking import EntityMasker
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
                        },
                        {
                            "date": "2024-03-04",
                            "type": "llm_exchange",
                            "data": {
                                "response": {
                                    "_usage": {
                                        "prompt_tokens": 100,
                                        "completion_tokens": 20,
                                        "total_tokens": 120,
                                    }
                                }
                            },
                        },
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
    assert agent["usage"]["llm_total_tokens"] == 120
    assert document["usage"]["llm_total_tokens"] == 120


def test_result_document_sanitizes_legacy_memory_payload_without_masking_timeline_dates():
    result = EngineResult(
        trading_days=1,
        start_date=date(2024, 3, 5),
        end_date=date(2024, 3, 5),
        agent_data={
            "agent": {
                "equity_curve": [(date(2024, 3, 5), Decimal("1000000"))],
                "trades": [],
                "memory_events": [
                    {
                        "event": "remember",
                        "date": "2024-03-05",
                        "content": "2024-03-04 贵州茅台与中国平安进入观察列表",
                    }
                ],
                "trajectory": {
                    "steps": [
                        {
                            "date": "2024-03-05",
                            "type": "assistant",
                            "data": {"content": "2024-03-04 中国平安值得研究"},
                        }
                    ]
                },
            }
        },
    )
    masker = EntityMasker(
        ["600519", "600000"],
        names={"600519": "贵州茅台", "600000": "浦发银行"},
        sanitize_aliases={"601318": ["中国平安"]},
        seed=1,
    )

    document = build_result_document(
        result,
        initial_cash=Decimal("1000000"),
        config={"mask_dates": True, "mask_entities": True},
        entity_masker=masker,
    )

    agent = document["agent_data"]["agent"]
    assert agent["memory_events"][0]["date"] == "2024-03-05"
    assert agent["trajectory"]["steps"][0]["date"] == "2024-03-05"
    visible = str(agent["memory_events"]) + str(agent["trajectory"])
    assert "2024-03-04" not in visible
    assert "贵州茅台" not in visible
    assert "中国平安" not in visible
    assert "外部公司" in visible
