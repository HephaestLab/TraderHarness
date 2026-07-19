"""Export full-fidelity masked trajectories as SFT JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SFTExportError(ValueError):
    """Raised when a result is unsafe or incomplete for SFT export."""


def _assistant_message(response: dict[str, Any]) -> dict[str, Any]:
    message = {key: value for key, value in response.items() if not str(key).startswith("_")}
    message.setdefault("role", "assistant")
    return message


def export_sft(
    source: str | Path,
    output: str | Path,
    *,
    allow_unmasked: bool = False,
    audit: bool = True,
) -> dict[str, Any]:
    """Export every exact LLM request/response pair as one OpenAI-style sample."""
    source_path = Path(source)
    output_path = Path(output)
    result = json.loads(source_path.read_text(encoding="utf-8"))
    if not allow_unmasked and not result.get("config", {}).get("mask_entities", False):
        raise SFTExportError(
            "SFT export requires an entity-masked result; rerun with --mask-entities"
        )

    records: list[dict[str, Any]] = []
    for agent_id, agent_data in result.get("agent_data", {}).items():
        steps = (agent_data.get("trajectory") or {}).get("steps", [])
        date_to_index: dict[str, int] = {}
        call_index = 0
        for step in steps:
            if step.get("type") != "llm_exchange":
                continue
            data = step.get("data") or {}
            messages = data.get("messages")
            response = data.get("response")
            if not isinstance(messages, list) or not isinstance(response, dict):
                raise SFTExportError("Malformed full-fidelity llm_exchange record")
            call_index += 1
            raw_date = str(step.get("date", ""))
            if raw_date not in date_to_index:
                date_to_index[raw_date] = len(date_to_index) + 1
            records.append(
                {
                    "messages": [*messages, _assistant_message(response)],
                    "tools": data.get("tools") or [],
                    "metadata": {
                        "agent_id": agent_id,
                        "phase": data.get("phase"),
                        "sub_window": data.get("sub_window"),
                        "day_index": date_to_index[raw_date],
                        "call_index": call_index,
                    },
                }
            )

    if not records:
        raise SFTExportError(
            "Result contains no full-fidelity llm_exchange records; "
            "legacy truncated trajectories cannot be exported"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    temporary.replace(output_path)

    audit_report = None
    if audit:
        from traderharness.audit import audit_artifacts

        audit_report = audit_artifacts([output_path])
        if not audit_report["passed"]:
            raise SFTExportError(
                f"SFT output failed leakage audit ({audit_report['finding_count']} findings)"
            )

    return {
        "source": str(source_path),
        "output": str(output_path),
        "examples": len(records),
        "agents": len(result.get("agent_data", {})),
        "audit": audit_report,
    }
