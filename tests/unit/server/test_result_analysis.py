from traderharness.result_analysis import MarketDatasetBarSource, build_result_analysis


def _document():
    return {
        "start_date": "2024-03-14",
        "end_date": "2024-03-15",
        "trading_days": 2,
        "agent_data": {
            "momentum": {
                "equity_curve": [
                    ["2024-03-14", 1_010_000],
                    ["2024-03-15", 990_000],
                ],
                "metrics": {"total_return_pct": -1.0, "sharpe_ratio": -0.4},
                "behavior": {"total_buy_count": 1, "total_sell_count": 0},
                "trades": [
                    {
                        "trade_date": "2024-03-14",
                        "stock_code": "000777",
                        "action": "buy",
                        "price": "10.5",
                        "quantity": 1000,
                        "amount": "10500",
                        "signal_reasoning": "趋势确认",
                        "window": "open_1",
                    }
                ],
                "trajectory": {
                    "days": [],
                    "steps": [
                        {
                            "date": "2024-03-14",
                            "step": 0,
                            "type": "morning_brief",
                            "data": {"content": "盘前市场偏强"},
                        },
                        {
                            "date": "2024-03-14",
                            "step": 1,
                            "type": "assistant",
                            "data": {
                                "phase": "pre_market",
                                "content": "研究趋势股",
                                "reasoning_content": "先检查量价，再确认风险。",
                            },
                        },
                        {
                            "date": "2024-03-14",
                            "step": 2,
                            "type": "tool_call",
                            "data": {
                                "name": "get_kline",
                                "args": {"stock_code": "000777", "days": 20},
                                "result": {
                                    "stock_code": "000777",
                                    "recent_20": [
                                        {
                                            "day": "D-2",
                                            "open": 9.8,
                                            "high": 10.1,
                                            "low": 9.7,
                                            "close": 10.0,
                                            "volume": 1200,
                                        },
                                        {
                                            "day": "D-1",
                                            "open": 10.0,
                                            "high": 10.6,
                                            "low": 9.9,
                                            "close": 10.5,
                                            "volume": 1800,
                                        },
                                    ],
                                },
                            },
                        },
                        {
                            "date": "2024-03-14",
                            "step": 3,
                            "type": "assistant",
                            "data": {
                                "phase": "open_window",
                                "sub_window": "open_1",
                                "content": "量价确认，按计划建立仓位。",
                                "reasoning_content": "突破有效，但仓位必须控制在上限内。",
                            },
                        },
                        {
                            "date": "2024-03-14",
                            "step": 4,
                            "type": "tool_call",
                            "data": {
                                "name": "place_order",
                                "args": {
                                    "stock_code": "000777",
                                    "action": "buy",
                                    "quantity": 1000,
                                },
                                "result": {
                                    "success": True,
                                    "price": 10.5,
                                    "quantity": 1000,
                                },
                            },
                        },
                    ],
                },
            }
        },
        "benchmark": {
            "name": "CSI 300",
            "equity_curve": [
                ["2024-03-14", 1_000_000],
                ["2024-03-15", 1_005_000],
            ],
        },
    }


def test_build_result_analysis_normalizes_research_evidence():
    analysis = build_result_analysis(_document())

    agent = analysis["agents"]["momentum"]
    assert agent["daily"][1]["drawdown_pct"] == -1.98
    assert agent["decisions"][0]["reasoning"] == "先检查量价，再确认风险。"
    assert agent["days"][0]["brief"] == "盘前市场偏强"
    assert agent["reasoning_coverage"] == {"responses": 2, "with_reasoning": 2}
    assert agent["tool_usage"] == [
        {"name": "get_kline", "count": 1},
        {"name": "place_order", "count": 1},
    ]

    security = agent["securities"]["000777"]
    assert security["bars"][0]["date"] == "2024-03-12"
    assert security["bars"][1]["date"] == "2024-03-13"
    assert security["markers"][0] == {
        "date": "2024-03-14",
        "side": "buy",
        "price": 10.5,
        "quantity": 1000,
        "reasoning": "趋势确认",
        "window": "open_1",
    }
    review = agent["trade_reviews"][0]
    assert review["id"] == "trade-1"
    assert review["code"] == "000777"
    assert review["bars"] == security["bars"]
    assert review["marker"] == security["markers"][0]
    assert review["decision_indices"] == [1]
    assert review["order_tool_index"] == 1
    assert review["evidence_status"] == "complete"


def test_trade_reviews_backfill_bars_from_evaluation_source_when_agent_never_queried_kline():
    document = _document()
    momentum = document["agent_data"]["momentum"]
    # A second fill on a stock the agent never called get_kline for.
    momentum["trades"].append(
        {
            "trade_date": "2024-03-14",
            "stock_code": "600001",
            "action": "buy",
            "price": 12.0,
            "quantity": 500,
            "amount": "6000",
            "signal_reasoning": "补仓",
            "window": "close_1",
        }
    )

    calls: list[tuple[str, str]] = []

    def evaluation_bars(code: str, trade_date: str) -> list[dict]:
        calls.append((code, trade_date))
        return [
            {"date": "2024-03-12", "open": 11.5, "high": 11.9, "low": 11.3, "close": 11.7, "volume": 900},
            {"date": "2024-03-13", "open": 11.7, "high": 12.1, "low": 11.6, "close": 11.9, "volume": 950},
        ]

    analysis = build_result_analysis(document, evaluation_bars=evaluation_bars)
    agent = analysis["agents"]["momentum"]

    # The originally-queried security is untouched and still trajectory evidence.
    original_review = agent["trade_reviews"][0]
    assert original_review["code"] == "000777"
    assert all(bar.get("source") == "trajectory" for bar in original_review["bars"])
    assert original_review["bars_source"] == "trajectory"

    backfilled_review = agent["trade_reviews"][1]
    assert backfilled_review["code"] == "600001"
    assert backfilled_review["bars"]
    assert all(bar["source"] == "evaluation" for bar in backfilled_review["bars"])
    assert backfilled_review["bars_source"] == "evaluation"
    assert backfilled_review["evidence_status"] == "partial"  # no decisions/order matched
    assert calls == [("600001", "2024-03-14")]

    # The provider is only consulted once per code even with a second fill.
    momentum["trades"].append(
        {
            "trade_date": "2024-03-15",
            "stock_code": "600001",
            "action": "sell",
            "price": 12.5,
            "quantity": 500,
            "amount": "6250",
            "signal_reasoning": "止盈",
            "window": "close_1",
        }
    )
    build_result_analysis(document, evaluation_bars=evaluation_bars)
    assert len(calls) <= 2  # provider is not called redundantly for bars already cached


def test_trade_reviews_have_no_bars_when_no_evaluation_source_is_configured():
    document = _document()
    document["agent_data"]["momentum"]["trades"].append(
        {
            "trade_date": "2024-03-14",
            "stock_code": "600001",
            "action": "buy",
            "price": 12.0,
            "quantity": 500,
            "signal_reasoning": "补仓",
            "window": "close_1",
        }
    )

    analysis = build_result_analysis(document)
    review = analysis["agents"]["momentum"]["trade_reviews"][1]

    assert review["bars"] == []
    assert review["bars_source"] == "none"
    assert review["evidence_status"] == "partial"


def test_market_dataset_bar_source_windows_around_trade_date_and_tags_none():
    import pandas as pd

    class FakeManager:
        def __init__(self):
            self.calls: list[list[str]] = []

        def load_daily_for_codes(self, codes):
            self.calls.append(list(codes))
            dates = [d.date() for d in pd.date_range("2024-02-01", periods=30, freq="B")]
            return pd.DataFrame(
                {
                    "date": dates,
                    "open": [10.0 + i * 0.1 for i in range(30)],
                    "high": [10.2 + i * 0.1 for i in range(30)],
                    "low": [9.9 + i * 0.1 for i in range(30)],
                    "close": [10.1 + i * 0.1 for i in range(30)],
                    "volume": [1000 + i for i in range(30)],
                }
            )

    manager = FakeManager()
    source = MarketDatasetBarSource(manager, before=5, after=2)

    anchor = str(pd.date_range("2024-02-01", periods=30, freq="B")[15].date())
    # anchor is the 16th business day, well inside the 30-day fixture window.
    bars = source(code="600001", trade_date=anchor)

    assert len(bars) == 7  # 5 before (incl. anchor) + 2 after
    assert bars[-3]["date"] == anchor
    assert all("source" not in bar for bar in bars)  # tagging is result_analysis's job
    assert manager.calls == [["600001"]]

    # A second call for the same code reuses the cached frame.
    source(code="600001", trade_date=anchor)
    assert manager.calls == [["600001"]]


def test_market_dataset_bar_source_returns_empty_for_missing_stock():
    class EmptyManager:
        def load_daily_for_codes(self, codes):
            import pandas as pd

            return pd.DataFrame()

    source = MarketDatasetBarSource(EmptyManager())
    assert source(code="000001", trade_date="2024-03-14") == []


def test_build_result_analysis_omits_comparison_for_single_agent():
    analysis = build_result_analysis(_document())
    assert analysis["comparison"] is None


def test_build_result_analysis_ranks_multiple_agents_by_total_return():
    document = _document()
    document["agent_data"]["contrarian"] = {
        "equity_curve": [
            ["2024-03-14", 1_020_000],
            ["2024-03-15", 1_040_000],
        ],
        "metrics": {
            "total_return_pct": 4.0,
            "sharpe_ratio": 1.8,
            "max_drawdown_pct": -0.5,
            "win_rate": 70.0,
        },
        "behavior": {"total_buy_count": 2, "total_sell_count": 1},
        "trades": [],
        "trajectory": {"steps": []},
    }

    analysis = build_result_analysis(document)
    comparison = analysis["comparison"]

    assert comparison["ranking"] == ["contrarian", "momentum"]
    assert comparison["agents"][0]["agent_id"] == "contrarian"
    assert comparison["agents"][0]["total_return_pct"] == 4.0
    assert comparison["agents"][0]["rank"] == 1
    assert comparison["agents"][1]["agent_id"] == "momentum"
    assert comparison["agents"][1]["rank"] == 2
    assert comparison["best_agent_id"] == "contrarian"


def test_build_result_analysis_keeps_legacy_assistant_content():
    document = _document()
    assistant = document["agent_data"]["momentum"]["trajectory"]["steps"][1]
    assistant["data"].pop("reasoning_content")

    decision = build_result_analysis(document)["agents"]["momentum"]["decisions"][0]

    assert decision["reasoning"] == ""
    assert decision["content"] == "研究趋势股"
    assert build_result_analysis(document)["agents"]["momentum"]["reasoning_coverage"] == {
        "responses": 2,
        "with_reasoning": 1,
    }
