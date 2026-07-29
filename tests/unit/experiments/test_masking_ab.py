import json

from traderharness.experiments.masking_ab import analyze_runs, run_experiment


def _record(condition, repetition, return_pct):
    return {
        "id": f"{condition}-r{repetition:02d}",
        "condition": condition,
        "repetition": repetition,
        "summary": {
            "metrics": {
                "total_return_pct": return_pct,
                "alpha_pct": return_pct - 0.5,
                "sharpe_ratio": return_pct / 2,
                "max_drawdown_pct": 1.0,
                "total_trades": 2,
                "final_value": 1_000_000 * (1 + return_pct / 100),
            },
            "behavior": {"tool_calls": 4, "decision_steps": 2},
            "llm_total_tokens": 100,
            "equity_curve": [],
        },
    }


def test_analyze_runs_reports_paired_unmasked_minus_masked_delta():
    analysis = analyze_runs(
        [
            _record("masked", 1, 1.0),
            _record("unmasked", 1, 3.0),
            _record("unmasked", 2, 2.0),
            _record("masked", 2, 1.0),
        ]
    )

    assert analysis["condition_summaries"]["masked"]["run_count"] == 2
    assert analysis["condition_summaries"]["unmasked"]["metrics"]["total_return_pct"] == 2.5
    assert analysis["paired_mean_unmasked_minus_masked"]["total_return_pct"] == 1.5


def test_run_experiment_writes_auditable_contract(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    counter = 0

    def fake_invoke(**kwargs):
        nonlocal counter
        counter += 1
        masked = kwargs["mask_dates"] and kwargs["mask_entities"]
        return_pct = 1.0 if masked else 2.0
        result_path = source / f"result-{counter}.json"
        result_path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "usage": {"llm_total_tokens": 50 + counter},
                    "agent_data": {
                        "agent": {
                            "metrics": {
                                "total_return_pct": return_pct,
                                "sharpe_ratio": 0.5,
                                "max_drawdown_pct": 0.2,
                                "total_trades": 1,
                                "final_value": 1_000_000 + return_pct * 10_000,
                            },
                            "vs_benchmark": {"alpha": return_pct - 0.25},
                            "trajectory": {
                                "steps": [
                                    {"type": "tool_call"},
                                    {"type": "decision"},
                                ]
                            },
                            "equity_curve": [["2024-03-14", 1_000_000 + return_pct * 10_000]],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        kwargs["record_replay"].write_text('{"type":"llm_call"}\n', encoding="utf-8")
        return {"result_path": result_path}

    def fake_audit(paths):
        is_unmasked = any("unmasked" in str(path) for path in paths)
        return {
            "passed": not is_unmasked,
            "finding_count": 2 if is_unmasked else 0,
            "findings": [] if not is_unmasked else [{"kind": "calendar_date"}],
            "note": "test",
        }

    monkeypatch.setattr("traderharness.experiments.masking_ab.audit_artifacts", fake_audit)
    monkeypatch.setattr(
        "traderharness.experiments.masking_ab._dataset_fingerprint", lambda: {"test": True}
    )
    monkeypatch.setattr("traderharness.experiments.masking_ab._endpoint_origin", lambda model: "test")
    monkeypatch.setattr("traderharness.experiments.masking_ab._git_commit", lambda: "abc123")
    output = tmp_path / "experiment"
    showcase = tmp_path / "showcase.json"

    outcome = run_experiment(
        invoke_run=fake_invoke,
        agent="agent",
        model="model",
        start_date="2024-03-14",
        end_date="2024-03-14",
        cash=1_000_000,
        repetitions=2,
        entity_mask_seed=42,
        output=output,
        showcase_output=showcase,
    )

    assert outcome["audit"]["masked"]["status"] == "pass"
    assert outcome["audit"]["unmasked"]["status"] == "expected_findings_for_control"
    assert len(json.loads((output / "manifest.json").read_text())["runs"]) == 4
    assert (output / "checksums.sha256").is_file()
    assert json.loads(showcase.read_text())["status"] == "complete"
