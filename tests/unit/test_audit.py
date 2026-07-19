import json

from traderharness.audit import audit_artifacts
from traderharness.core.leakage import EntityLeakDetector


def test_audit_artifacts_reports_leaks_with_locations(tmp_path):
    artifact = tmp_path / "trajectory.json"
    artifact.write_text(
        json.dumps({"steps": [{"content": "贵州茅台在2024年3月4日上涨"}]}),
        encoding="utf-8",
    )
    detector = EntityLeakDetector({"600519": {"贵州茅台"}})

    report = audit_artifacts([artifact], detector=detector)

    assert report["passed"] is False
    assert {finding["kind"] for finding in report["findings"]} == {
        "entity_alias",
        "calendar_date",
    }
    assert all(".steps[0].content" in finding["location"] for finding in report["findings"])


def test_audit_artifacts_accepts_masked_replay_cassette(tmp_path):
    artifact = tmp_path / "demo.jsonl"
    artifact.write_text(
        json.dumps(
            {
                "type": "llm_call",
                "output": {"content": "公司-600001在D+0暂不操作"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = audit_artifacts(
        [artifact],
        detector=EntityLeakDetector({"600519": {"贵州茅台"}}),
    )

    assert report["passed"] is True
    assert report["finding_count"] == 0
