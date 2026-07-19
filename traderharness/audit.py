"""Reusable leakage auditing for Agent-visible artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from traderharness.core.leakage import EntityLeakDetector
from traderharness.data.entity_templates import build_alias_map
from traderharness.data.stock_registry_loader import get_stock_registry
from traderharness.paths import dataset_dir

_METADATA_KEYS = {
    "date",
    "trade_date",
    "start_date",
    "end_date",
    "completed_at",
    "created_at",
    "generated_at",
    "equity_curve",
}


def artifact_strings(value: Any, location: str = "$") -> Iterable[tuple[str, str]]:
    """Yield Agent-visible strings and their JSON-style locations."""
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in _METADATA_KEYS:
                yield from artifact_strings(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from artifact_strings(item, f"{location}[{index}]")


def load_artifact(path: Path) -> Any:
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
        return frame.astype(object).where(pd.notna(frame), None).to_dict("records")
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return json.loads(path.read_text(encoding="utf-8"))


def build_leak_detector() -> EntityLeakDetector:
    announcements_path = dataset_dir() / "announcements.parquet"
    announcements = (
        pd.read_parquet(announcements_path, columns=["stock_code", "stock_name"])
        if announcements_path.exists()
        else None
    )
    return EntityLeakDetector(build_alias_map(get_stock_registry(), announcements))


def audit_artifacts(
    artifacts: Iterable[str | Path],
    *,
    max_findings: int = 100,
    detector: EntityLeakDetector | None = None,
) -> dict[str, Any]:
    """Audit artifacts and return a JSON-serializable report."""
    active_detector = detector or build_leak_detector()
    findings: list[dict[str, str]] = []
    for raw_path in artifacts:
        artifact = Path(raw_path)
        for location, text in artifact_strings(load_artifact(artifact), str(artifact)):
            for finding in active_detector.scan_text(text, location=location):
                findings.append(
                    {
                        "kind": finding.kind,
                        "value": finding.value,
                        "location": finding.location,
                    }
                )
                if len(findings) >= max_findings:
                    break
            if len(findings) >= max_findings:
                break
        if len(findings) >= max_findings:
            break

    return {
        "passed": not findings,
        "finding_count": len(findings),
        "findings": findings,
        "note": (
            "Pseudo-codes are a permutation of real-format A-share codes, so a static "
            "scanner cannot classify a bare six-digit code as real or masked."
        ),
    }
