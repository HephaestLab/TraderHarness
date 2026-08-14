"""Shared result persistence — used by both CLI and UI."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from traderharness.paths import results_dir
from traderharness.result_analysis import build_comparison

RESULTS_DIR = results_dir()
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_SCHEMA_VERSION = 1
ANALYSIS_SUMMARY_SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, payload: dict[str, Any], *, indent: int | None = None) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def generate_result_filename() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_result.json"


def result_summary_path(path: Path) -> Path:
    """Return the persistent lightweight-index path for a result artifact."""
    return path.with_name(f"{path.name}.summary.json")


def result_analysis_summary_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.analysis.summary.json")


def compact_result_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Drop full trajectory indexes while retaining each trade's linked evidence."""
    for agent in analysis.get("agents", {}).values():
        decisions = agent.get("decisions") or []
        tools = agent.get("tools") or []
        for review in agent.get("trade_reviews") or []:
            review["decisions"] = [
                decisions[index]
                for index in review.get("decision_indices") or []
                if isinstance(index, int) and 0 <= index < len(decisions)
            ]
            order_index = review.get("order_tool_index")
            review["order_tool"] = (
                tools[order_index]
                if isinstance(order_index, int) and 0 <= order_index < len(tools)
                else None
            )
        agent["days"] = []
        agent["decisions"] = []
        agent["tools"] = []
        agent["securities"] = {}
    analysis["detail"] = "summary"
    return analysis


def write_result_analysis_summary(
    path: Path,
    document: dict[str, Any],
    analysis: dict[str, Any] | None = None,
) -> Path:
    """Precompute the result page's first screen while the document is in memory."""
    from traderharness.result_analysis import build_result_analysis

    analysis = analysis or compact_result_analysis(build_result_analysis(document))
    stat = path.stat()
    payload = {
        "schema_version": ANALYSIS_SUMMARY_SCHEMA_VERSION,
        "artifact": {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
        },
        "document": {
            "start_date": document.get("start_date"),
            "end_date": document.get("end_date"),
            "config": document.get("config") or {},
        },
        "analysis": analysis,
    }
    sidecar = result_analysis_summary_path(path)
    _atomic_write_json(sidecar, payload)
    return sidecar


def read_result_analysis_summary(path: Path) -> dict[str, Any] | None:
    sidecar = result_analysis_summary_path(path)
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        stat = path.stat()
    except (OSError, json.JSONDecodeError):
        return None
    artifact = payload.get("artifact") or {}
    if (
        payload.get("schema_version") != ANALYSIS_SUMMARY_SCHEMA_VERSION
        or artifact.get("size") != stat.st_size
        or artifact.get("mtime_ns") != stat.st_mtime_ns
        or artifact.get("ctime_ns") != stat.st_ctime_ns
    ):
        return None
    if not isinstance(payload.get("analysis"), dict):
        return None
    return payload


def build_result_summary(document: dict[str, Any], filename: str) -> dict[str, Any]:
    """Build the small result-library row without retaining trajectory data."""
    summary: dict[str, Any] = {
        "file": filename,
        "status": document.get("status", "done"),
        "start_date": document.get("start_date")
        or (document.get("config") or {}).get("start_date"),
        "end_date": document.get("end_date")
        or (document.get("config") or {}).get("end_date"),
        "trading_days": document.get("trading_days", 0),
    }
    if document.get("status") == "failed" and document.get("error"):
        summary["error"] = str(document["error"])
    agent_data = document.get("agent_data") or {}
    summary["agent_count"] = len(agent_data)
    if len(agent_data) == 1:
        summary["metrics"] = next(iter(agent_data.values())).get("metrics") or {}
    elif len(agent_data) > 1:
        comparison = build_comparison(agent_data)
        if comparison:
            summary["agents"] = comparison["agents"]
            summary["best_agent_id"] = comparison["best_agent_id"]
            summary["best_return"] = comparison["agents"][0]["total_return_pct"]
    return summary


def write_result_summary(path: Path, document: dict[str, Any]) -> Path:
    """Persist a stamp-validated sidecar so listing never re-parses the artifact."""
    stat = path.stat()
    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "artifact": {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
        },
        "summary": build_result_summary(document, path.name),
    }
    sidecar = result_summary_path(path)
    _atomic_write_json(sidecar, payload)
    return sidecar


def read_result_summary(path: Path) -> dict[str, Any] | None:
    """Read a sidecar only when it still matches the underlying artifact."""
    sidecar = result_summary_path(path)
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        stat = path.stat()
    except (OSError, json.JSONDecodeError):
        return None
    artifact = payload.get("artifact") or {}
    if (
        payload.get("schema_version") != SUMMARY_SCHEMA_VERSION
        or artifact.get("size") != stat.st_size
        or artifact.get("mtime_ns") != stat.st_mtime_ns
        or artifact.get("ctime_ns") != stat.st_ctime_ns
    ):
        return None
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def ensure_result_summary(path: Path) -> dict[str, Any]:
    """Load a valid summary, backfilling one for legacy artifacts once."""
    summary = read_result_summary(path)
    if summary is not None:
        return summary
    document = json.loads(path.read_text(encoding="utf-8"))
    write_result_summary(path, document)
    return build_result_summary(document, path.name)


def backfill_result_summaries(root: Path | None = None) -> int:
    """Create or refresh summary sidecars for existing result artifacts."""
    updated = 0
    for path in (root or RESULTS_DIR).glob("*_result.json"):
        if read_result_summary(path) is not None:
            continue
        ensure_result_summary(path)
        updated += 1
    return updated


def save_pending(filename: str, config: dict) -> Path:
    """Write a pending (in-progress) result file. UI shows these as grey/running."""
    path = RESULTS_DIR / filename
    data = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "config": config,
    }
    _atomic_write_json(path, data, indent=2)
    write_result_summary(path, data)
    return path


def save_complete(filename: str, result_data: dict, *, status: str = "done") -> Path:
    """Durably commit a result, then materialize optional UI sidecars.

    Once the main artifact has been atomically replaced it is authoritative.
    A derived summary failure must not make callers overwrite that completed
    research result with a small ``failed`` placeholder.
    """
    path = RESULTS_DIR / filename
    result_data["status"] = status
    result_data["completed_at"] = datetime.now().isoformat()
    _atomic_write_json(path, result_data, indent=2)
    for label, writer in (
        ("result index", write_result_summary),
        ("result analysis", write_result_analysis_summary),
    ):
        try:
            writer(path, result_data)
        except Exception:
            logger.exception(
                "Completed result %s is durable, but the optional %s sidecar failed",
                path.name,
                label,
            )
    return path


def save_failed(filename: str, error: str, config: dict | None = None) -> Path:
    """Write a failed result file."""
    path = RESULTS_DIR / filename
    data = {
        "status": "failed",
        "error": error,
        "failed_at": datetime.now().isoformat(),
        "config": config,
    }
    _atomic_write_json(path, data, indent=2)
    write_result_summary(path, data)
    return path


def list_results() -> list[dict]:
    """List all result files with summary info."""
    results = []
    for f in sorted(RESULTS_DIR.glob("*_result.json"), reverse=True)[:30]:
        try:
            summary = ensure_result_summary(f)
            status = summary.get("status", "done")

            entry = {
                "file": f.name,
                "status": status,
                "date": summary.get("start_date", "?"),
            }

            if status == "done":
                metrics = summary.get("metrics")
                if metrics:
                    m = metrics
                    entry["return"] = m.get("total_return_pct", 0)
                    entry["sharpe"] = m.get("sharpe_ratio", 0)
                    entry["days"] = summary.get("trading_days", 0)

            results.append(entry)
        except Exception:
            pass
    return results
