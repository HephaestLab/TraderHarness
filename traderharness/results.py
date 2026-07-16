"""Shared result persistence — used by both CLI and UI."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path.home() / ".finharness" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_result_filename() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_result.json"


def save_pending(filename: str, config: dict) -> Path:
    """Write a pending (in-progress) result file. UI shows these as grey/running."""
    path = RESULTS_DIR / filename
    data = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "config": config,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_complete(filename: str, result_data: dict) -> Path:
    """Write a completed result file."""
    path = RESULTS_DIR / filename
    result_data["status"] = "done"
    result_data["completed_at"] = datetime.now().isoformat()
    path.write_text(
        json.dumps(result_data, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_results() -> list[dict]:
    """List all result files with summary info."""
    results = []
    for f in sorted(RESULTS_DIR.glob("*_result.json"), reverse=True)[:30]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            status = data.get("status", "done")

            entry = {
                "file": f.name,
                "status": status,
                "date": data.get("start_date", "?"),
            }

            if status == "done":
                agent_data = data.get("agent_data", {})
                if agent_data:
                    first = list(agent_data.values())[0]
                    m = first.get("metrics", {})
                    entry["return"] = m.get("total_return_pct", 0)
                    entry["sharpe"] = m.get("sharpe_ratio", 0)
                    entry["days"] = data.get("trading_days", 0)

            results.append(entry)
        except Exception:
            pass
    return results
