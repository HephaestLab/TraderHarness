"""Build auditable masked/unmasked A/B experiment artifacts."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from traderharness import __version__
from traderharness.audit import audit_artifacts
from traderharness.config.llm_settings import resolve_llm_credentials
from traderharness.paths import dataset_dir

CONDITIONS = {
    "masked": {"mask_dates": True, "mask_entities": True},
    "unmasked": {"mask_dates": False, "mask_entities": False},
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _endpoint_origin(model: str) -> str:
    _, raw_url = resolve_llm_credentials(model)
    if not raw_url:
        return "provider-default"
    parsed = urlsplit(raw_url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def _dataset_fingerprint() -> dict[str, Any]:
    root = dataset_dir()
    metadata = root / "metadata.json"
    daily = root / "daily.parquet"
    payload: dict[str, Any] = {
        "metadata_sha256": _sha256(metadata) if metadata.is_file() else None,
        "daily_size_bytes": daily.stat().st_size if daily.is_file() else None,
    }
    if metadata.is_file():
        try:
            payload["metadata"] = json.loads(metadata.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload["metadata"] = None
    return payload


def _agent_payload(result: dict[str, Any]) -> dict[str, Any]:
    agents = result.get("agent_data") or {}
    if not agents:
        raise ValueError("Result has no agent_data")
    agent_id, data = next(iter(agents.items()))
    trajectory = data.get("trajectory") or {}
    steps = trajectory.get("steps") or []
    metrics = data.get("metrics") or {}
    vs_benchmark = data.get("vs_benchmark") or {}
    return {
        "agent_id": agent_id,
        "metrics": {
            "total_return_pct": float(metrics.get("total_return_pct") or 0),
            "sharpe_ratio": float(metrics.get("sharpe_ratio") or 0),
            "max_drawdown_pct": float(metrics.get("max_drawdown_pct") or 0),
            "total_trades": int(metrics.get("total_trades") or 0),
            "final_value": float(metrics.get("final_value") or 0),
            "alpha_pct": float(vs_benchmark.get("alpha") or 0),
        },
        "behavior": {
            "tool_calls": sum(step.get("type") == "tool_call" for step in steps),
            "decision_steps": sum(step.get("type") == "decision" for step in steps),
        },
        "equity_curve": data.get("equity_curve") or [],
        "llm_total_tokens": int((result.get("usage") or {}).get("llm_total_tokens") or 0),
    }


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def analyze_runs(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Create descriptive condition aggregates and paired deltas."""
    by_condition: dict[str, list[dict[str, Any]]] = {name: [] for name in CONDITIONS}
    for record in run_records:
        by_condition[record["condition"]].append(record)

    condition_summaries: dict[str, Any] = {}
    metric_names = (
        "total_return_pct",
        "alpha_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "total_trades",
        "final_value",
    )
    for name, records in by_condition.items():
        aggregates: dict[str, float] = {}
        for metric in metric_names:
            aggregates[metric] = _mean(
                [float(record["summary"]["metrics"][metric]) for record in records]
            )
        aggregates["llm_total_tokens"] = _mean(
            [float(record["summary"]["llm_total_tokens"]) for record in records]
        )
        aggregates["tool_calls"] = _mean(
            [float(record["summary"]["behavior"]["tool_calls"]) for record in records]
        )
        condition_summaries[name] = {
            **CONDITIONS[name],
            "run_count": len(records),
            "metrics": aggregates,
        }

    pairs = []
    repetitions = sorted({int(record["repetition"]) for record in run_records})
    for repetition in repetitions:
        pair = {
            record["condition"]: record
            for record in run_records
            if int(record["repetition"]) == repetition
        }
        if set(pair) != set(CONDITIONS):
            continue
        deltas = {
            metric: (
                float(pair["unmasked"]["summary"]["metrics"][metric])
                - float(pair["masked"]["summary"]["metrics"][metric])
            )
            for metric in metric_names
        }
        pairs.append({"repetition": repetition, "unmasked_minus_masked": deltas})

    paired_means = {
        metric: _mean([pair["unmasked_minus_masked"][metric] for pair in pairs])
        for metric in metric_names
    }
    return {
        "condition_summaries": condition_summaries,
        "pairs": pairs,
        "paired_mean_unmasked_minus_masked": paired_means,
        "interpretation": (
            "Descriptive pilot only. Performance differences do not by themselves prove "
            "memorization, contamination, or causal model behavior."
        ),
    }


def _report_markdown(protocol: dict[str, Any], analysis: dict[str, Any], audits: dict[str, Any]) -> str:
    masked = analysis["condition_summaries"]["masked"]
    unmasked = analysis["condition_summaries"]["unmasked"]
    delta = analysis["paired_mean_unmasked_minus_masked"]
    def row(label: str, condition: dict[str, Any]) -> str:
        metrics = condition["metrics"]
        return (
            f"| {label} | {metrics['total_return_pct']:.4f}% | {metrics['alpha_pct']:.4f}% | "
            f"{metrics['sharpe_ratio']:.4f} | {metrics['max_drawdown_pct']:.4f}% | "
            f"{metrics['total_trades']:.2f} | {metrics['llm_total_tokens']:.0f} |"
        )

    return f"""# Masked vs Unmasked pilot report

Generated: {datetime.now(timezone.utc).isoformat()}

Model: `{protocol['model']}`

Window: `{protocol['start_date']}` to `{protocol['end_date']}`

Paired repetitions: {protocol['repetitions']}

## Protocol

The same agent, market data, starting cash, tools and execution engine were run under two
conditions. `masked` hides calendar dates and company identities. `unmasked` exposes both as an
explicit research control. Run order alternated by repetition.

## Aggregate results

| Condition | Return | Alpha vs CSI 300 | Sharpe | Max drawdown | Trades | Tokens |
|---|---:|---:|---:|---:|---:|---:|
{row('Masked', masked)}
{row('Unmasked control', unmasked)}

Mean paired return delta (unmasked minus masked): **{delta['total_return_pct']:+.4f} percentage points**.

## Audit

- Masked artifacts: **{audits['masked']['status']}**, {audits['masked']['finding_count']} findings.
- Unmasked control: **{audits['unmasked']['status']}**,
  {audits['unmasked']['finding_count']} expected date/entity findings retained for inspection.

## Limitations

- This pilot is descriptive and deliberately small; it does not support a significance claim.
- Provider-side model updates and residual sampling variance can affect paired runs.
- A performance difference alone does not prove memorization or benchmark contamination.
- Results are historical research artifacts, not investment advice or a model ranking.
"""


def _showcase(
    protocol: dict[str, Any],
    manifest: dict[str, Any],
    analysis: dict[str, Any],
    audits: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    for name in CONDITIONS:
        records = [record for record in run_records if record["condition"] == name]
        latest_curve = records[-1]["summary"]["equity_curve"] if records else []
        conditions[name] = {
            "label": "Masked" if name == "masked" else "Unmasked control",
            **CONDITIONS[name],
            "audit": {
                "status": audits[name]["status"],
                "finding_count": audits[name]["finding_count"],
            },
            "metrics": analysis["condition_summaries"][name]["metrics"],
            "runs": [
                {
                    "id": record["id"],
                    "repetition": record["repetition"],
                    "metrics": record["summary"]["metrics"],
                    "llm_total_tokens": record["summary"]["llm_total_tokens"],
                }
                for record in records
            ],
            "equity_curve": latest_curve,
        }
    return {
        "schema_version": 1,
        "experiment_id": protocol["experiment_id"],
        "status": "complete",
        "generated_at": manifest["completed_at"],
        "title": "Masked vs Unmasked LLM Trading Agent",
        "summary": (
            "The same agent was evaluated with and without visible calendar dates and company "
            "identities. Inspect the recorded, auditable pilot below."
        ),
        "model": protocol["model"],
        "window": {"start": protocol["start_date"], "end": protocol["end_date"]},
        "repetitions": protocol["repetitions"],
        "commit": manifest["git_commit"],
        "dataset_fingerprint": manifest["dataset_fingerprint"],
        "conditions": conditions,
        "paired_deltas": analysis["paired_mean_unmasked_minus_masked"],
        "limitations": [
            "This is a recorded research experiment, not a live backtest or investment recommendation.",
            analysis["interpretation"],
        ],
    }


def run_experiment(
    *,
    invoke_run: Callable[..., dict[str, Any]],
    agent: str,
    model: str,
    start_date: str,
    end_date: str,
    cash: int,
    repetitions: int,
    entity_mask_seed: int,
    output: Path,
    showcase_output: Path | None = None,
) -> dict[str, Any]:
    """Execute paired live runs and finalize a self-auditing artifact directory."""
    output = output.resolve()
    runs_dir = output / "runs"
    replays_dir = output / "replays"
    runs_dir.mkdir(parents=True, exist_ok=True)
    replays_dir.mkdir(parents=True, exist_ok=True)
    protocol = {
        "schema_version": 1,
        "experiment_id": f"masking-ab-{start_date}-{end_date}-pilot",
        "hypothesis": (
            "Visible dates and company identities may systematically change the behavior of the "
            "same LLM trading agent."
        ),
        "agent": agent,
        "model": model,
        "start_date": start_date,
        "end_date": end_date,
        "initial_cash": cash,
        "repetitions": repetitions,
        "entity_mask_seed": entity_mask_seed,
        "conditions": CONDITIONS,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(output / "protocol.json", protocol)

    records: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        order = ["masked", "unmasked"] if repetition % 2 else ["unmasked", "masked"]
        for condition in order:
            flags = CONDITIONS[condition]
            run_id = f"{condition}-r{repetition:02d}"
            replay_path = replays_dir / f"{run_id}.jsonl"
            outcome = invoke_run(
                agent=agent,
                start=start_date,
                end=end_date,
                model=model,
                cash=cash,
                mask_dates=flags["mask_dates"],
                mask_entities=flags["mask_entities"],
                entity_mask_seed=entity_mask_seed,
                replay=None,
                record_replay=replay_path,
            )
            if not outcome or "result_path" not in outcome:
                raise RuntimeError(f"Run {run_id} did not return a result artifact")
            source_result = Path(outcome["result_path"])
            target_result = runs_dir / f"{run_id}-result.json"
            shutil.copy2(source_result, target_result)
            result_document = json.loads(target_result.read_text(encoding="utf-8"))
            records.append(
                {
                    "id": run_id,
                    "condition": condition,
                    "repetition": repetition,
                    "order_in_pair": order.index(condition) + 1,
                    "result": str(target_result.relative_to(output)).replace("\\", "/"),
                    "replay": str(replay_path.relative_to(output)).replace("\\", "/"),
                    "summary": _agent_payload(result_document),
                }
            )

    analysis = analyze_runs(records)
    _write_json(output / "analysis.json", analysis)
    audits: dict[str, Any] = {}
    for condition in CONDITIONS:
        artifacts = []
        for record in records:
            if record["condition"] == condition:
                artifacts.extend([output / record["result"], output / record["replay"]])
        report = audit_artifacts(artifacts)
        if condition == "masked" and not report["passed"]:
            raise RuntimeError(
                f"Masked experiment artifacts failed leakage audit ({report['finding_count']} findings)"
            )
        audits[condition] = {
            **report,
            "status": "pass" if report["passed"] else "expected_findings_for_control",
            "artifacts": [str(path.relative_to(output)).replace("\\", "/") for path in artifacts],
        }
    _write_json(output / "audit.json", audits)

    manifest = {
        "schema_version": 1,
        "experiment_id": protocol["experiment_id"],
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "traderharness_version": __version__,
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "model": model,
        "endpoint": _endpoint_origin(model),
        "dataset_fingerprint": _dataset_fingerprint(),
        "runs": records,
    }
    _write_json(output / "manifest.json", manifest)
    (output / "report.md").write_text(
        _report_markdown(protocol, analysis, audits), encoding="utf-8"
    )
    showcase = _showcase(protocol, manifest, analysis, audits, records)
    _write_json(output / "showcase.json", showcase)
    if showcase_output is not None:
        _write_json(showcase_output, showcase)

    files = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "checksums.sha256"
    )
    checksum_lines = [
        f"{_sha256(path)}  {str(path.relative_to(output)).replace(chr(92), '/')}" for path in files
    ]
    (output / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return {"output": output, "manifest": manifest, "analysis": analysis, "audit": audits}
