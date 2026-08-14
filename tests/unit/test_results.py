import json
from pathlib import Path

from traderharness import results


def _document(return_pct: float = 3.5) -> dict:
    return {
        "status": "done",
        "start_date": "2026-03-02",
        "end_date": "2026-08-01",
        "trading_days": 105,
        "agent_data": {
            "agent": {
                "metrics": {"total_return_pct": return_pct, "sharpe_ratio": 0.8},
                "trades": [],
            }
        },
    }


def test_save_complete_writes_a_stamp_validated_summary_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path)

    path = results.save_complete("20260810_120000_result.json", _document())

    sidecar = results.result_summary_path(path)
    assert sidecar.is_file()
    assert sidecar.name == "20260810_120000_result.json.summary.json"
    analysis_sidecar = results.result_analysis_summary_path(path)
    assert analysis_sidecar.is_file()
    assert results.read_result_analysis_summary(path)["analysis"]["detail"] == "summary"
    assert results.read_result_summary(path) == {
        "file": path.name,
        "status": "done",
        "start_date": "2026-03-02",
        "end_date": "2026-08-01",
        "trading_days": 105,
        "agent_count": 1,
        "metrics": {"total_return_pct": 3.5, "sharpe_ratio": 0.8},
    }


def test_legacy_result_summary_is_backfilled_once_and_invalidated_on_rewrite(tmp_path):
    path = tmp_path / "20260810_120000_result.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")

    first = results.ensure_result_summary(path)
    assert first["metrics"]["total_return_pct"] == 3.5
    assert results.read_result_summary(path) == first

    path.write_text(json.dumps(_document(9.0)), encoding="utf-8")
    assert results.read_result_summary(path) is None
    assert results.ensure_result_summary(path)["metrics"]["total_return_pct"] == 9.0


def test_valid_sidecar_avoids_reading_the_large_result(tmp_path, monkeypatch):
    path = tmp_path / "20260810_120000_result.json"
    document = _document()
    path.write_text(json.dumps(document), encoding="utf-8")
    results.write_result_summary(path, document)
    original_read_text = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        if self == path:
            raise AssertionError("large result artifact should not be read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    assert results.ensure_result_summary(path)["metrics"]["total_return_pct"] == 3.5


def test_completed_artifact_survives_optional_analysis_sidecar_failure(
    tmp_path, monkeypatch
):
    """UI materialization must never downgrade an already durable backtest."""
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path)

    def fail_analysis(*args, **kwargs):
        raise OSError(22, "analysis sidecar unavailable")

    monkeypatch.setattr(results, "write_result_analysis_summary", fail_analysis)

    path = results.save_complete("20260810_120000_result.json", _document())

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["status"] == "done"
    assert results.read_result_summary(path)["status"] == "done"
    assert not results.result_analysis_summary_path(path).exists()


def test_failed_summary_exposes_error_without_opening_full_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path)

    path = results.save_failed(
        "20260810_120000_result.json",
        "ReplayMismatchError: request diverged",
        {"start_date": "2026-03-02", "end_date": "2026-08-01"},
    )

    summary = results.read_result_summary(path)
    assert summary["status"] == "failed"
    assert summary["error"] == "ReplayMismatchError: request diverged"
