"""CLI entry point — traderharness run/data/benchmark/ui."""

from __future__ import annotations

import hashlib
from pathlib import Path

import click
from dotenv import load_dotenv

from traderharness import __version__
from traderharness._hashseed import ensure_fixed_hash_seed

load_dotenv()


def _replay_provenance(
    path: Path | None,
    *,
    mask_dates: bool = False,
    anchor=None,
) -> dict:
    if path is None:
        return {"mode": "live"}
    artifact = path / "manifest.json" if path.is_dir() else path
    artifact_name = artifact.name
    if mask_dates and anchor is not None:
        from traderharness.core.masking import DateMasker

        artifact_name = DateMasker(anchor=anchor).mask_text(artifact_name)
    return {
        "mode": "replay",
        "artifact": artifact_name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }


@click.group()
@click.version_option(version=__version__)
def main():
    """TraderHarness — LLM-native trading agent harness."""
    # Pin the hash seed (re-exec once if unset) so sandboxed agent code —
    # which runs in-process — produces identical set iteration order in the
    # recording process and every later replay process.
    ensure_fixed_hash_seed()


def _is_committee(agent) -> bool:
    """True if `agent` is a ToolAgent/PromptAgent wired with a committee."""
    loop = getattr(agent, "_loop", None)
    return bool(loop is not None and getattr(loop, "committee", None) is not None)


@main.command()
@click.option("--agent", "-a", required=True, help="Agent card ID or YAML config path")
@click.option("--start", "-s", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", required=True, help="End date (YYYY-MM-DD)")
@click.option("--model", "-m", default=None, help="Override model (for example: deepseek-v4-pro)")
@click.option("--cash", default=1000000, help="Initial cash (default: 1000000)")
@click.option(
    "--mask-dates/--no-mask-dates",
    default=True,
    help="Replace calendar dates with relative dates in every agent-visible surface",
)
@click.option(
    "--mask-entities/--no-mask-entities",
    default=True,
    help="Anonymize company codes and names for contamination-resistant evaluation",
)
@click.option("--entity-mask-seed", default=0, type=int, help="Deterministic entity mapping seed")
@click.option(
    "--replay",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Replay recorded LLM responses without an API key. Accepts either a "
        "v1 single-file JSONL cassette or a Replay Bundle directory "
        "(required for a committee's advisors)"
    ),
)
@click.option(
    "--record-replay",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Record sanitized LLM responses. A path ending in .jsonl records a "
        "v1 single-file cassette; any other path records a Replay Bundle "
        "directory (manifest.json + one cassette per agent/advisor)"
    ),
)
def run(
    agent: str,
    start: str,
    end: str,
    model: str | None,
    cash: int,
    mask_dates: bool,
    mask_entities: bool,
    entity_mask_seed: int,
    replay: Path | None,
    record_replay: Path | None,
):
    """Run a backtest with the specified agent card."""
    import asyncio
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from traderharness.config.llm_settings import resolve_llm_credentials
    from traderharness.results import (
        RESULTS_DIR,
        generate_result_filename,
        save_complete,
        save_failed,
        save_pending,
    )
    from traderharness.trajectory.bundle import (
        ScopedReplayPlayer,
        ScopedReplayRecorder,
        executor_scope_id,
        is_bundle_path,
    )
    from traderharness.trajectory.replay import ReplayPlayer, ReplayRecorder

    if replay is not None and record_replay is not None:
        raise click.UsageError("--replay and --record-replay are mutually exclusive")

    replay_is_bundle = replay is not None and is_bundle_path(replay)
    record_is_bundle = record_replay is not None and is_bundle_path(record_replay)

    from traderharness.agents.tool_agent import CONTRACT_VERSION

    replay_player = ReplayPlayer(replay) if replay is not None and not replay_is_bundle else None
    bundle_player = ScopedReplayPlayer(replay) if replay_is_bundle else None
    if bundle_player is not None:
        mask_dates = bundle_player.manifest.mask_dates
        mask_entities = bundle_player.manifest.mask_entities
        entity_mask_seed = bundle_player.manifest.entity_mask_seed
    # New single-file recordings embed the live contract version so replay can
    # reinject the same system prompt (legacy files without meta stay on v1).
    replay_recorder = (
        ReplayRecorder(
            prompt_contract_version=CONTRACT_VERSION,
            entity_mask_style="opaque",
        )
        if record_replay is not None and not record_is_bundle
        else None
    )
    bundle_recorder = ScopedReplayRecorder() if record_is_bundle else None
    if bundle_player is not None:
        prompt_contract_version = bundle_player.manifest.prompt_contract_version
    elif replay_player is not None:
        prompt_contract_version = replay_player.prompt_contract_version
    elif replay_recorder is not None:
        prompt_contract_version = CONTRACT_VERSION
    else:
        prompt_contract_version = None

    # Resolve agent
    agent_path = Path(agent)
    if agent_path.exists() and agent_path.suffix in (".yaml", ".yml"):
        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.prompt_agent import PromptAgent

        if bundle_player is not None or bundle_recorder is not None:
            agent_obj = PromptAgent(
                agent_path,
                replay_recorder=bundle_recorder,
                replay_player=bundle_player,
                prompt_contract_version=prompt_contract_version,
                mask_dates=mask_dates,
            )
        elif replay_player is not None or replay_recorder is not None:
            import yaml

            agent_config = yaml.safe_load(agent_path.read_text(encoding="utf-8")) or {}
            if agent_config.get("advisors"):
                raise click.UsageError(
                    "Committee replay with a single-file cassette is not supported; "
                    "use a Replay Bundle directory for --replay/--record-replay instead"
                )
            use_model = model or agent_config.get("model", "deepseek-chat")
            llm_override = LLMClient(
                model=use_model,
                api_key="replay" if replay_player is not None else None,
                cache_enabled=False,
                replay_recorder=replay_recorder,
                replay_player=replay_player,
            )
            agent_obj = PromptAgent(agent_path, llm_client=llm_override, mask_dates=mask_dates)
        else:
            agent_obj = PromptAgent(agent_path, mask_dates=mask_dates)
        agent_id = agent_obj.agent_id
        click.echo(f"Agent (YAML): {agent_obj.name}")
    else:
        from traderharness.agents.agent_card import load_card
        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent

        card = load_card(agent)
        if not card:
            click.echo(f"Error: Agent card '{agent}' not found.", err=True)
            click.echo("Available cards:", err=True)
            from traderharness.agents.agent_card import list_cards

            for c in list_cards():
                click.echo(f"  {c.id} -- {c.name}", err=True)
            raise SystemExit(1)

        use_model = model or card.model
        resolved_key, resolved_url = resolve_llm_credentials(use_model)

        if bundle_player is not None or bundle_recorder is not None:
            scope = executor_scope_id(card.id, is_committee=False)
            scoped_player = bundle_player.scope(scope) if bundle_player is not None else None
            scoped_recorder = bundle_recorder.scope(scope) if bundle_recorder is not None else None
            api_key = "replay" if scoped_player is not None else resolved_key
            if not api_key:
                click.echo(
                    "Error: 未配置 LLM API Key。请设置环境变量 DEEPSEEK_API_KEY，或在 Web 控制台设置页配置。",
                    err=True,
                )
                raise SystemExit(1)
            llm = LLMClient(
                model=use_model,
                api_key=api_key,
                base_url=resolved_url,
                cache_enabled=False,
                replay_recorder=scoped_recorder,
                replay_player=scoped_player,
            )
        else:
            api_key = "replay" if replay_player is not None else resolved_key
            if not api_key:
                click.echo(
                    "Error: 未配置 LLM API Key。请设置环境变量 DEEPSEEK_API_KEY，或在 Web 控制台设置页配置。",
                    err=True,
                )
                raise SystemExit(1)
            llm = LLMClient(
                model=use_model,
                api_key=api_key,
                base_url=resolved_url,
                cache_enabled=False,
                replay_recorder=replay_recorder,
                replay_player=replay_player,
            )
        agent_obj = ToolAgent(
            agent_id=card.id,
            name=card.name,
            llm_client=llm,
            persona=card.persona,
            initial_cash=Decimal(str(cash)),
            max_positions=card.max_positions,
            max_position_pct=card.max_position_pct,
            max_pre_iterations=card.max_pre_iterations,
            max_window_iterations=card.max_window_iterations,
            require_structured_plan=card.require_structured_plan,
            require_decision_card=card.require_decision_card,
            require_phase_completion=card.require_phase_completion,
            minimum_holding_days=card.minimum_holding_days,
            research_interval_days=card.research_interval_days,
            sandbox_pre_market_only=card.sandbox_pre_market_only,
            sandbox_max_calls_per_day=card.sandbox_max_calls_per_day,
            watchlist_ttl_days=card.watchlist_ttl_days,
            max_active_memories=card.max_active_memories,
            max_daily_memories=card.max_daily_memories,
            allowed_tools=card.allowed_tools,
            mask_dates=mask_dates,
            prompt_contract_version=prompt_contract_version,
        )
        agent_id = card.id
        click.echo(f"Agent (Card): {card.name}")

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    initial_cash = Decimal(str(cash))

    click.echo(f"Period: {start_date} -> {end_date}")
    click.echo(f"Cash: {cash:,}")

    # Write pending result (UI sees this as "running")
    result_filename = generate_result_filename()
    live_file = RESULTS_DIR / result_filename.replace("_result.json", "_live.jsonl")
    config = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "initial_cash": cash,
        "model": agent_obj.llm_client.model,
        "agent_id": agent_id,
        "mask_dates": mask_dates,
        "mask_entities": mask_entities,
        "entity_mask_seed": entity_mask_seed,
        "entity_mask_style": (
            bundle_player.manifest.entity_mask_style
            if bundle_player is not None
            else replay_player.entity_mask_style
            if replay_player is not None
            else "opaque"
        ),
        "provenance": _replay_provenance(
            replay,
            mask_dates=mask_dates,
            anchor=start_date,
        ),
    }
    save_pending(result_filename, config)

    # Each run receives a clean sandbox workspace. This prevents an earlier
    # experiment's scratch features or scripts from contaminating a rerun,
    # while preserving files across all trading days within this run.
    agent_obj.workspace_root = str(
        RESULTS_DIR.parent / "workspaces" / result_filename.removesuffix("_result.json") / agent_id
    )

    # Set live file on agent for real-time streaming
    agent_obj._trajectory._live_file = Path(live_file)
    agent_obj._trajectory._live_file.parent.mkdir(parents=True, exist_ok=True)
    agent_obj._trajectory._live_file.write_text("", encoding="utf-8")

    click.echo(f"Result: ~/.traderharness/results/{result_filename}")
    click.echo(f"Web result: /results?file={result_filename} (auto-refreshes until complete)")
    click.echo(f"Live: {live_file.name}")
    if not mask_dates or not mask_entities:
        click.echo(
            "WARNING: unmasked research control enabled; outputs may contain real dates or entities.",
            err=True,
        )
    click.echo("Running...")

    complete_path = None
    try:
        from traderharness.core.engine import BacktestEngine, EngineConfig
        from traderharness.core.events import EventBus
        from traderharness.metrics.benchmark import load_csi300_curve
        from traderharness.run_results import build_result_document

        engine = BacktestEngine(
            EngineConfig(
                initial_cash=initial_cash,
                mask_entities=mask_entities,
                entity_mask_seed=entity_mask_seed,
                entity_mask_style=(
                    bundle_player.manifest.entity_mask_style
                    if bundle_player is not None
                    else replay_player.entity_mask_style
                    if replay_player is not None
                    else "opaque"
                ),
            ),
            event_bus=EventBus(),
        )

        async def run_and_close_clients():
            try:
                return await engine.run([agent_obj], start_date, end_date)
            finally:
                clients = [getattr(agent_obj, "llm_client", None)]
                committee = getattr(agent_obj, "committee", None)
                clients.extend(getattr(advisor, "llm_client", None) for advisor in getattr(committee, "advisors", []))
                for client in clients:
                    close = getattr(client, "aclose", None)
                    if close is not None:
                        await close()

        result = asyncio.run(run_and_close_clients())

        benchmark_curve = load_csi300_curve(start_date, end_date, initial_cash)
        result_data = build_result_document(
            result,
            initial_cash=initial_cash,
            config=config,
            benchmark_curve=benchmark_curve,
            entity_masker=engine._entity_masker,
        )

        if replay_player is not None:
            replay_player.assert_consumed()
        if bundle_player is not None:
            bundle_player.assert_all_consumed()
        if replay_recorder is not None and record_replay is not None:
            from traderharness.audit import audit_artifacts

            replay_recorder.save(record_replay)
            config["recorded_replay"] = _replay_provenance(
                record_replay,
                mask_dates=mask_dates,
                anchor=start_date,
            )
            audit_report = audit_artifacts([record_replay])
            if not audit_report["passed"]:
                if mask_dates and mask_entities:
                    raise RuntimeError(
                        f"Recorded replay failed leakage audit ({audit_report['finding_count']} findings)"
                    )
                click.echo(
                    "Replay leakage audit: EXPECTED FINDINGS "
                    f"({audit_report['finding_count']}; unmasked research control)"
                )
            else:
                click.echo("Replay leakage audit: PASS")
            click.echo(f"Replay: {record_replay}")
        if bundle_recorder is not None and record_replay is not None:
            from datetime import datetime, timezone

            from traderharness import __version__ as th_version
            from traderharness.audit import audit_artifacts
            from traderharness.trajectory.bundle import AgentManifestEntry, ReplayBundleManifest

            manifest = ReplayBundleManifest(
                start_date=start_date,
                end_date=end_date,
                initial_cash=float(cash),
                mask_dates=mask_dates,
                mask_entities=mask_entities,
                entity_mask_seed=entity_mask_seed,
                entity_mask_style="opaque",
                agents=[
                    AgentManifestEntry(
                        id=agent_id,
                        name=getattr(agent_obj, "name", agent_id),
                        model=model or "deepseek-chat",
                        cassette=(f"{executor_scope_id(agent_id, is_committee=_is_committee(agent_obj))}.jsonl"),
                    )
                ],
                prompt_contract_version=getattr(agent_obj, "prompt_contract_version", "v1"),
                created_at=datetime.now(timezone.utc).isoformat(),
                traderharness_version=th_version,
            )
            manifest_path = bundle_recorder.save_bundle(record_replay, manifest)
            config["recorded_replay"] = _replay_provenance(
                record_replay,
                mask_dates=mask_dates,
                anchor=start_date,
            )
            artifacts = [manifest_path] + [
                record_replay / "agents" / f"{scope}.jsonl" for scope in bundle_recorder.scope_ids
            ]
            audit_report = audit_artifacts(artifacts)
            if not audit_report["passed"]:
                if mask_dates and mask_entities:
                    raise RuntimeError(
                        f"Recorded replay bundle failed leakage audit ({audit_report['finding_count']} findings)"
                    )
                click.echo(
                    "Replay leakage audit: EXPECTED FINDINGS "
                    f"({audit_report['finding_count']}; unmasked research control)"
                )
            else:
                click.echo("Replay leakage audit: PASS")
            click.echo(f"Replay bundle: {record_replay}")
        complete_path = save_complete(result_filename, result_data)

        # Clean up live file
        if live_file.exists():
            live_file.unlink()

        metrics = result_data["agent_data"][agent_id]["metrics"]
        vs_benchmark = result_data["agent_data"][agent_id]["vs_benchmark"]
        try:
            click.echo(f"\nDone! {result.trading_days} trading days")
            click.echo(f"  Return: {metrics['total_return_pct']:+.2f}%")
            click.echo(f"  Sharpe: {metrics['sharpe_ratio']:.2f}")
            click.echo(f"  Max DD: -{metrics['max_drawdown_pct']:.2f}%")
            click.echo(f"  Trades: {metrics['total_trades']}")
            if vs_benchmark:
                click.echo(
                    f"  CSI 300: {vs_benchmark['benchmark_return_pct']:+.2f}% | Alpha: {vs_benchmark['alpha']:+.2f}%"
                )
        except OSError as output_error:
            # A long-running CLI may outlive its supervising terminal or pipe.
            # The completed research artifact must remain authoritative even
            # when best-effort terminal output can no longer be delivered.
            if getattr(output_error, "errno", None) not in {22, 32}:
                raise
        return {
            "result_path": complete_path,
            "result": result_data,
            "replay_path": record_replay,
        }

    except Exception as e:
        # Never overwrite an already persisted, auditable result merely
        # because post-run cleanup or terminal output failed.
        if complete_path is None:
            save_failed(result_filename, str(e), config)
        if live_file.exists():
            live_file.unlink()
        click.echo(f"\nFailed: {e}", err=True)
        import traceback

        traceback.print_exc()
        raise SystemExit(1)


@main.command()
def demo():
    """Run the bundled real-market replay without an API key."""
    from importlib.resources import as_file, files

    cassette = files("traderharness.demo").joinpath("momentum_dragon_2024-03-14.jsonl")
    source_cassette = Path(__file__).resolve().parents[1] / "examples" / "replays" / "momentum_dragon_2024-03-14.jsonl"
    selected = cassette if cassette.is_file() else source_cassette
    if not selected.is_file():
        raise click.ClickException("Bundled replay cassette is missing from this installation")
    with as_file(selected) as cassette_path:
        click.get_current_context().invoke(
            run,
            agent="momentum-dragon",
            start="2024-03-14",
            end="2024-03-14",
            model=None,
            cash=1_000_000,
            mask_dates=True,
            mask_entities=True,
            entity_mask_seed=42,
            replay=cassette_path,
            record_replay=None,
        )


@main.command("masking-ab")
@click.option("--agent", "-a", default="momentum-dragon", show_default=True)
@click.option("--model", "-m", default="deepseek-v4-pro", show_default=True)
@click.option("--start", default="2024-03-04", show_default=True)
@click.option("--end", default="2024-03-15", show_default=True)
@click.option("--cash", default=1_000_000, type=click.IntRange(min=1), show_default=True)
@click.option("--repetitions", default=3, type=click.IntRange(min=1, max=20), show_default=True)
@click.option("--entity-mask-seed", default=42, type=int, show_default=True)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("artifacts/masking-ab-pilot"),
    show_default=True,
)
@click.option(
    "--showcase-output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Also write the sanitized browser showcase JSON to this path",
)
def masking_ab(
    agent: str,
    model: str,
    start: str,
    end: str,
    cash: int,
    repetitions: int,
    entity_mask_seed: int,
    output: Path,
    showcase_output: Path | None,
):
    """Run a paired, recorded and audited masked/unmasked pilot."""
    from traderharness.experiments.masking_ab import run_experiment

    ctx = click.get_current_context()
    click.echo(f"Frozen masking A/B protocol: {repetitions} pair(s), {start} -> {end}, model={model}")
    outcome = run_experiment(
        invoke_run=lambda **kwargs: ctx.invoke(run, **kwargs),
        agent=agent,
        model=model,
        start_date=start,
        end_date=end,
        cash=cash,
        repetitions=repetitions,
        entity_mask_seed=entity_mask_seed,
        output=output,
        showcase_output=showcase_output,
    )
    click.echo(f"Experiment: {outcome['output']}")
    click.echo("Masked audit: PASS")
    unmasked = outcome["audit"]["unmasked"]
    click.echo(f"Unmasked control audit: {unmasked['status']} ({unmasked['finding_count']} findings retained)")


@main.command()
@click.option(
    "--agent",
    "-a",
    "agent_specs",
    multiple=True,
    required=True,
    help="Repeat for each agent card ID or YAML path",
)
@click.option("--start", "-s", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", required=True, help="End date (YYYY-MM-DD)")
@click.option("--cash", default=1000000, help="Initial cash per agent")
@click.option(
    "--mask-dates/--no-mask-dates",
    default=True,
    help="Replace calendar dates with relative dates in every agent-visible surface",
)
@click.option(
    "--mask-entities/--no-mask-entities",
    default=True,
    help="Use one shared run-scoped entity permutation",
)
@click.option("--entity-mask-seed", default=0, type=int)
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option(
    "--replay",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Replay a Replay Bundle directory: each agent (and any committee "
        "advisors) is matched to its scoped cassette by agent id"
    ),
)
@click.option(
    "--record-replay",
    type=click.Path(path_type=Path),
    default=None,
    help="Record every agent's (and advisors') LLM calls to a Replay Bundle directory",
)
def compare(
    agent_specs,
    start: str,
    end: str,
    cash: int,
    mask_dates: bool,
    mask_entities: bool,
    entity_mask_seed: int,
    output,
    replay: Path | None,
    record_replay: Path | None,
):
    """Run independent agents and produce a ranked HTML report."""
    import asyncio
    import json
    import os
    from collections import Counter
    from dataclasses import asdict
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from pathlib import Path

    from traderharness import __version__ as th_version
    from traderharness.agents.agent_card import load_card
    from traderharness.agents.llm_client import LLMClient
    from traderharness.agents.prompt_agent import PromptAgent
    from traderharness.agents.tool_agent import ToolAgent
    from traderharness.config.llm_settings import resolve_llm_credentials
    from traderharness.core.engine import AgentExecutionError, BacktestEngine, EngineConfig
    from traderharness.metrics.behavior import calculate_behavior
    from traderharness.metrics.benchmark import load_csi300_curve
    from traderharness.metrics.comparison import compare_multi_agents
    from traderharness.metrics.comparison_report import write_comparison_html
    from traderharness.paths import results_dir
    from traderharness.trajectory.bundle import (
        AgentManifestEntry,
        ReplayBundleManifest,
        ScopedReplayPlayer,
        ScopedReplayRecorder,
        executor_scope_id,
        is_bundle_path,
    )

    if len(agent_specs) < 2:
        raise click.UsageError("compare requires at least two --agent values")
    if replay is not None and record_replay is not None:
        raise click.UsageError("--replay and --record-replay are mutually exclusive")
    if replay is not None and not is_bundle_path(replay):
        raise click.UsageError(
            "compare --replay requires a Replay Bundle directory: with multiple "
            "agents (and possible committee advisors), a single v1 cassette "
            "cannot provide independently scoped cassettes"
        )

    replay_player = ScopedReplayPlayer(replay) if replay is not None else None
    replay_recorder = ScopedReplayRecorder() if record_replay is not None else None
    if replay_player is not None:
        mask_dates = replay_player.manifest.mask_dates
        mask_entities = replay_player.manifest.mask_entities
        entity_mask_seed = replay_player.manifest.entity_mask_seed
    prompt_contract_version = replay_player.manifest.prompt_contract_version if replay_player is not None else None

    initial_cash = Decimal(str(cash))
    agents = []
    for spec in agent_specs:
        path = Path(spec)
        if path.exists() and path.suffix in {".yaml", ".yml"}:
            agent = PromptAgent(
                path,
                replay_recorder=replay_recorder,
                replay_player=replay_player,
                prompt_contract_version=prompt_contract_version,
                mask_dates=mask_dates,
            )
        else:
            card = load_card(spec)
            if not card:
                raise click.ClickException(f"Agent card '{spec}' not found")
            scope = executor_scope_id(card.id, is_committee=False)
            scoped_player = replay_player.scope(scope) if replay_player is not None else None
            scoped_recorder = replay_recorder.scope(scope) if replay_recorder is not None else None
            resolved_key, resolved_url = resolve_llm_credentials(card.model)
            api_key = "replay" if scoped_player is not None else resolved_key
            if not api_key:
                raise click.ClickException(
                    "未配置 LLM API Key。请设置环境变量 DEEPSEEK_API_KEY，或在 Web 控制台设置页配置。"
                )
            llm = LLMClient(
                model=card.model,
                api_key=api_key,
                base_url=resolved_url,
                cache_enabled=False,
                max_retries=int(os.environ.get("TRADERHARNESS_LLM_MAX_RETRIES", "6")),
                replay_recorder=scoped_recorder,
                replay_player=scoped_player,
            )
            agent = ToolAgent(
                agent_id=card.id,
                name=card.name,
                llm_client=llm,
                persona=card.persona,
                initial_cash=initial_cash,
                max_positions=card.max_positions,
                max_position_pct=card.max_position_pct,
                max_pre_iterations=card.max_pre_iterations,
                max_window_iterations=card.max_window_iterations,
                require_structured_plan=card.require_structured_plan,
                require_decision_card=card.require_decision_card,
                require_phase_completion=card.require_phase_completion,
                minimum_holding_days=card.minimum_holding_days,
                research_interval_days=card.research_interval_days,
                sandbox_pre_market_only=card.sandbox_pre_market_only,
                sandbox_max_calls_per_day=card.sandbox_max_calls_per_day,
                watchlist_ttl_days=card.watchlist_ttl_days,
                max_active_memories=card.max_active_memories,
                max_daily_memories=card.max_daily_memories,
                allowed_tools=card.allowed_tools,
                mask_dates=mask_dates,
                prompt_contract_version=prompt_contract_version,
            )
        agents.append(agent)
    ids = [agent.agent_id for agent in agents]
    if len(ids) != len(set(ids)):
        raise click.UsageError("agent IDs must be unique")

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    engine = BacktestEngine(
        EngineConfig(
            initial_cash=initial_cash,
            mask_entities=mask_entities,
            entity_mask_seed=entity_mask_seed,
            entity_mask_style=(replay_player.manifest.entity_mask_style if replay_player is not None else "opaque"),
        )
    )
    click.echo(f"Running {len(agents)} agents: {', '.join(ids)} ({start_date} -> {end_date})")
    if not mask_dates or not mask_entities:
        click.echo(
            "WARNING: unmasked research control enabled; outputs may contain real dates or entities.",
            err=True,
        )

    async def _run_compare():
        # Create the limiter inside the running loop (3.10+ requirement).
        limiter = asyncio.Semaphore(int(os.environ.get("TRADERHARNESS_LLM_CONCURRENCY", "2")))
        if replay_player is None:
            for agent in agents:
                client = getattr(agent, "llm_client", None)
                if client is not None:
                    client._concurrency_limiter = limiter
        return await engine.run(agents, start_date, end_date)

    try:
        engine_result = asyncio.run(_run_compare())
    except AgentExecutionError as exc:
        click.echo(f"\nFailed: {exc}", err=True)
        for agent_id, reason in exc.result.failed_agents.items():
            click.echo(f"  [{agent_id}] {reason}", err=True)
        raise SystemExit(1) from exc

    if replay_player is not None:
        replay_player.assert_all_consumed()
    if replay_recorder is not None and record_replay is not None:
        sample_client = next(
            (getattr(agent, "llm_client", None) for agent in agents),
            None,
        )
        thinking_meta = {
            "enabled": bool(getattr(sample_client, "_thinking", False)),
            "effort": getattr(sample_client, "_reasoning_effort", None),
        }
        manifest = ReplayBundleManifest(
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(cash),
            mask_dates=mask_dates,
            mask_entities=mask_entities,
            entity_mask_seed=entity_mask_seed,
            entity_mask_style="opaque",
            agents=[
                AgentManifestEntry(
                    id=agent.agent_id,
                    name=getattr(agent, "name", agent.agent_id),
                    model=getattr(agent.llm_client, "model", ""),
                    cassette=(f"{executor_scope_id(agent.agent_id, is_committee=_is_committee(agent))}.jsonl"),
                )
                for agent in agents
            ],
            prompt_contract_version=next(
                (
                    getattr(agent, "prompt_contract_version")
                    for agent in agents
                    if hasattr(agent, "prompt_contract_version")
                ),
                "v1",
            ),
            thinking=thinking_meta,
            created_at=datetime.now(timezone.utc).isoformat(),
            traderharness_version=th_version,
        )
        manifest_path = replay_recorder.save_bundle(record_replay, manifest)
        click.echo(f"Replay bundle: {record_replay}")
        # Defer leakage audit until after comparison artifacts are written so a
        # long live run is never discarded solely because audit failed last.
        _pending_audit_artifacts = [manifest_path] + [
            record_replay / "agents" / f"{scope}.jsonl" for scope in replay_recorder.scope_ids
        ]
    else:
        _pending_audit_artifacts = None
    benchmark_curve = load_csi300_curve(start_date, end_date, initial_cash)
    comparison = compare_multi_agents(engine_result, initial_cash, benchmark_curve)
    frame = comparison.to_dataframe()
    ranks = {agent_id: index + 1 for index, (agent_id, _) in enumerate(comparison.ranking)}
    frame.insert(0, "Rank", frame["Agent"].map(ranks))
    frame = frame.sort_values("Rank")
    rows = frame.to_dict("records")

    entity_masker = getattr(engine, "_entity_masker", None)
    behavior = {}
    for agent_id, data in engine_result.agent_data.items():
        steps = (data.get("trajectory") or {}).get("steps", [])
        counts = Counter(step.get("date") for step in steps if step.get("type") == "tool_call")
        tool_calls = [counts.get(str(day), 0) for day, _ in data["equity_curve"]]
        metrics = asdict(
            calculate_behavior(
                data["trades"],
                data["equity_curve"],
                initial_cash,
                tool_calls,
            )
        )
        behavior[agent_id] = entity_masker.mask_obj(metrics) if entity_masker is not None else metrics

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = output or results_dir() / f"{stamp}_comparison.html"
    write_comparison_html(html_path, rows, behavior)
    json_path = Path(html_path).with_suffix(".json")
    agent_runs = {}
    for agent_id, data in engine_result.agent_data.items():
        trades = data["trades"]
        conditional_orders = data.get("conditional_orders", [])
        conditional_order_events = data.get("conditional_order_events", [])
        memory_events = data.get("memory_events", [])
        if entity_masker is not None:
            trades = entity_masker.mask_obj(trades)
            conditional_orders = entity_masker.mask_obj(conditional_orders)
            conditional_order_events = entity_masker.mask_obj(conditional_order_events)
            memory_events = entity_masker.mask_obj(memory_events)
        agent_runs[agent_id] = {
            "equity_curve": [(str(day), float(value)) for day, value in data["equity_curve"]],
            "trades": trades,
            "conditional_orders": conditional_orders,
            "conditional_order_events": conditional_order_events,
            "memory_events": memory_events,
            "trajectory": data.get("trajectory"),
        }
    json_path.write_text(
        json.dumps(
            {
                "start_date": start,
                "end_date": end,
                "mask_dates": mask_dates,
                "mask_entities": mask_entities,
                "entity_mask_seed": entity_mask_seed,
                "entity_mask_style": (
                    replay_player.manifest.entity_mask_style if replay_player is not None else "opaque"
                ),
                "comparison": rows,
                "behavior": behavior,
                "agent_runs": agent_runs,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    click.echo(frame.to_string(index=False))
    click.echo(f"HTML: {html_path}")
    click.echo(f"JSON: {json_path}")

    if _pending_audit_artifacts is not None:
        from traderharness.audit import audit_artifacts

        audit_report = audit_artifacts(_pending_audit_artifacts)
        if not audit_report["passed"]:
            if mask_dates and mask_entities:
                raise click.ClickException(
                    f"Recorded replay bundle failed leakage audit "
                    f"({audit_report['finding_count']} findings); "
                    f"comparison was still written to {html_path}"
                )
            click.echo(
                f"Replay leakage audit: EXPECTED FINDINGS ({audit_report['finding_count']}; unmasked research control)"
            )
        else:
            click.echo("Replay leakage audit: PASS")


@main.command()
@click.argument(
    "artifacts",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--json-output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--max-findings", type=click.IntRange(min=1), default=100, show_default=True)
def audit(artifacts: tuple[Path, ...], json_output: Path | None, max_findings: int):
    """Audit masked JSON, JSONL, or Parquet ARTIFACTS for leakage."""
    import json

    from traderharness.audit import audit_artifacts

    report = audit_artifacts(artifacts, max_findings=max_findings)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(payload, encoding="utf-8")
    click.echo(payload)
    if not report["passed"]:
        raise SystemExit(1)


@main.group("export")
def export_group():
    """Export masked run artifacts for downstream training."""


@export_group.command("sft")
@click.argument(
    "source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option(
    "--allow-unmasked",
    is_flag=True,
    help="Explicitly permit identity-bearing source trajectories",
)
def export_sft_command(source: Path, output: Path, allow_unmasked: bool):
    """Export full-fidelity LLM exchanges from a result JSON."""
    from traderharness.trajectory.sft import SFTExportError, export_sft

    try:
        report = export_sft(source, output, allow_unmasked=allow_unmasked)
    except SFTExportError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Examples: {report['examples']}")
    click.echo(f"Agents: {report['agents']}")
    click.echo(f"Output: {output}")
    click.echo("Leakage audit: PASS")


@main.group()
def data():
    """Manage local and downloadable datasets."""


@data.command("list")
def data_list():
    """List available downloadable datasets."""
    from traderharness.data.datasets import list_datasets

    datasets = list_datasets()
    click.echo("Available datasets:")
    for item in datasets:
        status = "[x]" if item["downloaded"] else "[ ]"
        click.echo(f"  {status} {item['name']} — {item['description']}")


@data.command("download")
@click.option("--dataset", "-d", default=None, help="Named micro-dataset")
@click.option("--full", "full_dataset", is_flag=True, help="Install the canonical 5-year dataset")
@click.option("--force", is_flag=True, help="Atomically replace an existing local dataset")
def data_download(dataset: str | None, full_dataset: bool, force: bool):
    """Download a named micro-dataset or the full canonical dataset."""
    from traderharness.data.datasets import download_full, ensure_dataset

    if bool(dataset) == full_dataset:
        raise click.UsageError("Choose exactly one of --dataset NAME or --full")
    if full_dataset:
        click.echo("Downloading and verifying the full dataset...")
        path = download_full(force=force)
    else:
        if force:
            raise click.UsageError("--force is only valid with --full")
        click.echo(f"Downloading {dataset}...")
        path = ensure_dataset(dataset)
    click.echo(f"Downloaded to: {path}")


@data.command("update")
@click.option(
    "--only",
    default="daily,5min,valuation,fundamentals,dividends,announcements,news,benchmark",
    help=(
        "Comma-separated: daily,5min,valuation,fundamentals,dividends,"
        "announcements,news,benchmark"
    ),
)
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--end", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--dry-run", is_flag=True, help="Show watermarks without network or writes")
def data_update(only: str, since, end, dry_run: bool):
    """Incrementally update canonical local datasets from upstream sources."""
    from traderharness.data.update_providers import (
        Baostock5MinProvider,
        BaostockCsi300Provider,
        BaostockDailyProvider,
        BaostockDividendsProvider,
        BaostockFundamentalsProvider,
        BaostockValuationProvider,
        CascadingMinuteProvider,
        ClsNewsProvider,
        CninfoAnnouncementsProvider,
        Eastmoney5MinProvider,
    )
    from traderharness.data.updater import DataUpdater, UpdatePlan
    from traderharness.paths import dataset_dir

    selected = {item.strip() for item in only.split(",") if item.strip()}
    updater = DataUpdater(
        dataset_dir(),
        daily_provider=BaostockDailyProvider(),
        min5_provider=CascadingMinuteProvider(
            Eastmoney5MinProvider(cache_dir=dataset_dir() / ".update_cache" / "eastmoney_5min"),
            Baostock5MinProvider(),
        ),
        valuation_provider=BaostockValuationProvider(),
        fundamentals_provider=BaostockFundamentalsProvider(),
        dividends_provider=BaostockDividendsProvider(),
        announcements_provider=CninfoAnnouncementsProvider(),
        news_provider=ClsNewsProvider(),
        benchmark_provider=BaostockCsi300Provider(),
    )
    result = updater.update(
        only=selected,
        since=since.date() if since else None,
        end=end.date() if end else None,
        dry_run=dry_run,
    )
    for name, value in result.items():
        if isinstance(value, UpdatePlan):
            click.echo(f"{name}: {value.start} -> {value.end}")
        else:
            click.echo(f"{name}: rows {value.rows_before:,} -> {value.rows_after:,} (+{value.rows_added:,})")


@data.command("status")
def data_status():
    """Show canonical watermarks and the latest resumable pipeline state."""
    from traderharness.data.coverage import DatasetCoverage
    from traderharness.paths import dataset_dir

    status = DatasetCoverage(dataset_dir()).status()
    click.echo(f"Dataset: {status['root']}")
    for name, watermark in status["watermarks"].items():
        click.echo(f"  {name:13} {watermark or 'missing'}")
    pipeline = status.get("pipeline") or {}
    if pipeline:
        click.echo(
            f"Latest pipeline: {pipeline.get('status', 'unknown')} "
            f"({pipeline.get('run_id', 'unknown')})"
        )


@data.command("doctor")
@click.option("--start", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--end", type=click.DateTime(formats=["%Y-%m-%d"]), default=None)
@click.option("--daily-only", is_flag=True, help="Do not require minute-bar coverage")
def data_doctor(start, end, daily_only: bool):
    """Fail closed unless the requested backtest interval is fully covered."""
    from datetime import date as date_type

    from traderharness.data.coverage import DataCoverageError, DatasetCoverage
    from traderharness.paths import dataset_dir

    end_date = end.date() if end else date_type.today()
    start_date = start.date() if start else end_date
    try:
        report = DatasetCoverage(dataset_dir()).assert_backtest_ready(
            start_date,
            end_date,
            require_minute=not daily_only,
        )
    except DataCoverageError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Dataset coverage: READY")
    click.echo(f"  requested: {report['start']} -> {report['end']}")
    click.echo(f"  target session: {report['target_session']}")
    for name, watermark in report["watermarks"].items():
        click.echo(f"  {name:13} {watermark}")


@main.command()
def agents():
    """List available agent cards."""
    from traderharness.agents.agent_card import list_cards

    cards = list_cards()
    if not cards:
        click.echo("No agent cards found. Create one via the UI (traderharness ui).")
        return
    click.echo("Agent Cards:")
    for c in cards:
        click.echo(f"  {c.id} -- {c.name} (model: {c.model})")


@main.command()
def results():
    """List recent backtest results."""
    from traderharness.results import list_results

    all_results = list_results()
    if not all_results:
        click.echo("No results yet.")
        return
    click.echo("Recent Results:")
    for r in all_results[:15]:
        status = r["status"]
        if status == "done":
            ret = r.get("return", 0)
            click.echo(f"  [{status}] {r['date']} | {ret:+.2f}% | {r['file']}")
        elif status == "running":
            click.echo(f"  [{status}] {r.get('date', '?')} | {r['file']}")
        else:
            click.echo(f"  [{status}] {r['file']}")


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", "-p", default=8000, type=click.IntRange(1, 65535), show_default=True)
@click.option(
    "--allow-public",
    is_flag=True,
    help="Acknowledge the arbitrary-code-execution risk of non-local binding",
)
def ui(host: str, port: int, allow_public: bool):
    """Launch the local FastAPI web application."""
    local_hosts = {"127.0.0.1", "::1", "localhost"}
    if host not in local_hosts and not allow_public:
        raise click.UsageError(
            "TraderHarness is local-only because execute_code can run arbitrary code. "
            "Pass --allow-public only if you accept this risk."
        )
    if host not in local_hosts:
        click.echo(
            "WARNING: exposing TraderHarness grants clients code execution on this host.",
            err=True,
        )
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("Web dependencies missing. Install traderharness[ui].") from exc
    click.echo(f"TraderHarness UI: http://{host}:{port}")
    uvicorn.run(
        "traderharness.server.app:create_app",
        factory=True,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
