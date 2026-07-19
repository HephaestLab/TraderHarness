import json

import pytest

from traderharness.trajectory.sft import SFTExportError, export_sft


def _masked_result():
    return {
        "config": {"mask_entities": True},
        "agent_data": {
            "momentum": {
                "trajectory": {
                    "steps": [
                        {
                            "date": "2024-03-14",
                            "step": 7,
                            "type": "llm_exchange",
                            "data": {
                                "phase": "open_window",
                                "sub_window": "open_1",
                                "messages": [
                                    {"role": "system", "content": "交易规则"},
                                    {"role": "user", "content": "D+0 开盘"},
                                ],
                                "tools": [
                                    {
                                        "type": "function",
                                        "function": {"name": "place_order"},
                                    }
                                ],
                                "response": {
                                    "role": "assistant",
                                    "content": "买入公司-600001",
                                    "reasoning_content": "趋势确认",
                                    "tool_calls": [
                                        {
                                            "id": "call-1",
                                            "type": "function",
                                            "function": {
                                                "name": "place_order",
                                                "arguments": '{"stock_code":"600001"}',
                                            },
                                        }
                                    ],
                                    "_usage": {"total_tokens": 100},
                                },
                            },
                        }
                    ]
                }
            }
        },
    }


def test_exports_full_fidelity_openai_messages_without_absolute_date(tmp_path):
    source = tmp_path / "result.json"
    source.write_text(json.dumps(_masked_result(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "sft.jsonl"

    report = export_sft(source, output, audit=False)

    record = json.loads(output.read_text(encoding="utf-8"))
    assert report["examples"] == 1
    assert record["messages"][-1]["content"] == "买入公司-600001"
    assert record["messages"][-1]["reasoning_content"] == "趋势确认"
    assert record["messages"][-1]["tool_calls"][0]["function"]["name"] == "place_order"
    assert "_usage" not in record["messages"][-1]
    assert record["tools"][0]["function"]["name"] == "place_order"
    assert record["metadata"] == {
        "agent_id": "momentum",
        "phase": "open_window",
        "sub_window": "open_1",
        "day_index": 1,
        "call_index": 1,
    }
    assert "2024-03-14" not in output.read_text(encoding="utf-8")


def test_rejects_unmasked_results_by_default(tmp_path):
    result = _masked_result()
    result["config"]["mask_entities"] = False
    source = tmp_path / "result.json"
    source.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(SFTExportError, match="entity-masked"):
        export_sft(source, tmp_path / "sft.jsonl", audit=False)


def test_rejects_legacy_truncated_trajectory_without_llm_exchanges(tmp_path):
    result = _masked_result()
    result["agent_data"]["momentum"]["trajectory"]["steps"][0]["type"] = "assistant"
    source = tmp_path / "result.json"
    source.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(SFTExportError, match="full-fidelity"):
        export_sft(source, tmp_path / "sft.jsonl", audit=False)
