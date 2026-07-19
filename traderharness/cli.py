"""CLI entry point — traderharness run/data/benchmark/ui."""

from __future__ import annotations

from pathlib import Path

import click
from dotenv import load_dotenv

from traderharness import __version__

load_dotenv()


@click.group()
@click.version_option(version=__version__)
def main():
    """TraderHarness — LLM-native trading agent harness."""
    pass


def _is_committee(agent) -> bool:
    """True if `agent` is a ToolAgent/PromptAgent wired with a committee."""
    loop = getattr(agent, "_loop", None)
    return bool(loop is not None and getattr(loop, "committee", None) is not None)


@main.command()
@click.option("--agent", "-a", required=True, help="Agent card ID or YAML config path")
@click.option("--start", "-s", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", required=True, help="End date (YYYY-MM-DD)")
@click.option(
    "--model", "-m", default=None, help="Override model (deepseek-chat, deepseek-v4-flash)"
)
@click.option("--cash", default=1000000, help="Initial cash (default: 1000000)")
@click.option(
    "--mask-entities/--no-mask-entities",
    default=False,
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
    mask_entities: bool,
    entity_mask_seed: int,
    replay: Path | None,
    record_replay: Path | None,
):
    """Run a backtest with the specified agent card."""
    import asyncio
    import os
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

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
    # New single-file recordings embed the live contract version so replay can
    # reinject the same system prompt (legacy files without meta stay on v1).
    replay_recorder = (
        ReplayRecorder(prompt_contract_version=CONTRACT_VERSION)
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
            agent_obj = PromptAgent(agent_path, llm_client=llm_override)
        else:
            agent_obj = PromptAgent(agent_path)
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
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "")

        if bundle_player is not None or bundle_recorder is not None:
            scope = executor_scope_id(card.id, is_committee=False)
            scoped_player = bundle_player.scope(scope) if bundle_player is not None else None
            scoped_recorder = (
                bundle_recorder.scope(scope) if bundle_recorder is not None else None
            )
            api_key = "replay" if scoped_player is not None else os.environ.get(
                "DEEPSEEK_API_KEY", ""
            )
            if not api_key:
                click.echo("Error: DEEPSEEK_API_KEY not set.", err=True)
                raise SystemExit(1)
            llm = LLMClient(
                model=use_model,
                api_key=api_key,
                base_url=base_url,
                cache_enabled=False,
                replay_recorder=scoped_recorder,
                replay_player=scoped_player,
            )
        else:
            api_key = (
                "replay" if replay_player is not None else os.environ.get("DEEPSEEK_API_KEY", "")
            )
            if not api_key:
                click.echo("Error: DEEPSEEK_API_KEY not set.", err=True)
                raise SystemExit(1)
            llm = LLMClient(
                model=use_model,
                api_key=api_key,
                base_url=base_url,
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
            allowed_tools=card.allowed_tools,
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
    live_file = RESULTS_DIR / result_filename.replace("_result.json", "_live.json")
    config = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "initial_cash": cash,
        "model": agent_obj.llm_client.model,
        "agent_id": agent_id,
        "mask_entities": mask_entities,
        "entity_mask_seed": entity_mask_seed,
    }
    save_pending(result_filename, config)

    # Set live file on agent for real-time streaming
    agent_obj._trajectory._live_file = Path(live_file)
    agent_obj._trajectory._live_file.parent.mkdir(parents=True, exist_ok=True)
    agent_obj._trajectory._live_file.write_text("[]", encoding="utf-8")

    click.echo(f"Result: ~/.traderharness/results/{result_filename}")
    click.echo(f"Live: {live_file.name}")
    click.echo("Running...")

    try:
        from dataclasses import asdict

        from traderharness.core.engine import BacktestEngine, EngineConfig
        from traderharness.core.events import EventBus
        from traderharness.metrics.behavior import calculate_behavior
        from traderharness.metrics.benchmark import load_csi300_curve
        from traderharness.metrics.comparison import compare_vs_benchmark
        from traderharness.metrics.performance import calculate_metrics

        engine = BacktestEngine(
            EngineConfig(
                initial_cash=initial_cash,
                mask_entities=mask_entities,
                entity_mask_seed=entity_mask_seed,
            ),
            event_bus=EventBus(),
        )
        result = asyncio.run(engine.run([agent_obj], start_date, end_date))

        data = result.agent_data[agent_id]
        metrics = calculate_metrics(data["equity_curve"], initial_cash, data["trades"])
        benchmark_curve = load_csi300_curve(start_date, end_date, initial_cash)
        vs_benchmark = (
            compare_vs_benchmark(data["equity_curve"], benchmark_curve, initial_cash)
            if benchmark_curve
            else None
        )
        steps = (data.get("trajectory") or {}).get("steps", [])
        tool_calls_by_date = {}
        for step in steps:
            if step.get("type") == "tool_call":
                key = step.get("date")
                tool_calls_by_date[key] = tool_calls_by_date.get(key, 0) + 1
        tool_call_counts = [tool_calls_by_date.get(str(day), 0) for day, _ in data["equity_curve"]]
        behavior = calculate_behavior(
            data["trades"],
            data["equity_curve"],
            initial_cash,
            tool_call_counts,
        )
        persisted_trades = data["trades"]
        persisted_behavior = asdict(behavior)
        if engine._entity_masker is not None:
            persisted_trades = engine._entity_masker.mask_obj(persisted_trades)
            persisted_behavior = engine._entity_masker.mask_obj(persisted_behavior)

        result_data = {
            "trading_days": result.trading_days,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "config": config,
            "agent_data": {
                agent_id: {
                    "equity_curve": [(str(d), float(v)) for d, v in data["equity_curve"]],
                    "trades": persisted_trades,
                    "trajectory": data.get("trajectory"),
                    "behavior": persisted_behavior,
                    "vs_benchmark": asdict(vs_benchmark) if vs_benchmark else None,
                    "metrics": {
                        "total_return_pct": metrics.total_return_pct,
                        "annual_return_pct": metrics.annual_return_pct,
                        "sharpe_ratio": metrics.sharpe_ratio,
                        "sortino_ratio": metrics.sortino_ratio,
                        "max_drawdown_pct": metrics.max_drawdown_pct,
                        "win_rate": metrics.win_rate,
                        "profit_loss_ratio": metrics.profit_loss_ratio,
                        "total_trades": metrics.total_trades,
                        "final_value": metrics.final_value,
                    },
                }
            },
            "benchmark": (
                {
                    "name": "CSI 300",
                    "equity_curve": [(str(d), float(v)) for d, v in benchmark_curve],
                }
                if benchmark_curve
                else None
            ),
        }

        if replay_player is not None:
            replay_player.assert_consumed()
        if bundle_player is not None:
            bundle_player.assert_all_consumed()
        if replay_recorder is not None and record_replay is not None:
            from traderharness.audit import audit_artifacts

            replay_recorder.save(record_replay)
            audit_report = audit_artifacts([record_replay])
            if not audit_report["passed"]:
                raise RuntimeError(
                    f"Recorded replay failed leakage audit "
                    f"({audit_report['finding_count']} findings)"
                )
            click.echo(f"Replay: {record_replay}")
            click.echo("Replay leakage audit: PASS")
        if bundle_recorder is not None and record_replay is not None:
            from datetime import UTC, datetime

            from traderharness import __version__ as th_version
            from traderharness.audit import audit_artifacts
            from traderharness.trajectory.bundle import AgentManifestEntry, ReplayBundleManifest

            manifest = ReplayBundleManifest(
                start_date=start_date,
                end_date=end_date,
                initial_cash=float(cash),
                mask_entities=mask_entities,
                entity_mask_seed=entity_mask_seed,
                agents=[
                    AgentManifestEntry(
                        id=agent_id,
                        name=getattr(agent_obj, "name", agent_id),
                        model=model or "deepseek-chat",
                        cassette=(
                            f"{executor_scope_id(agent_id, is_committee=_is_committee(agent_obj))}"
                            ".jsonl"
                        ),
                    )
                ],
                prompt_contract_version=getattr(agent_obj, "prompt_contract_version", "v1"),
                created_at=datetime.now(UTC).isoformat(),
                traderharness_version=th_version,
            )
            manifest_path = bundle_recorder.save_bundle(record_replay, manifest)
            artifacts = [manifest_path] + [
                record_replay / "agents" / f"{scope}.jsonl" for scope in bundle_recorder.scope_ids
            ]
            audit_report = audit_artifacts(artifacts)
            if not audit_report["passed"]:
                raise RuntimeError(
                    f"Recorded replay bundle failed leakage audit "
                    f"({audit_report['finding_count']} findings)"
                )
            click.echo(f"Replay bundle: {record_replay}")
            click.echo("Replay leakage audit: PASS")
        save_complete(result_filename, result_data)

        # Clean up live file
        if live_file.exists():
            live_file.unlink()

        click.echo(f"\nDone! {result.trading_days} trading days")
        click.echo(f"  Return: {metrics.total_return_pct:+.2f}%")
        click.echo(f"  Sharpe: {metrics.sharpe_ratio:.2f}")
        click.echo(f"  Max DD: -{metrics.max_drawdown_pct:.2f}%")
        click.echo(f"  Trades: {metrics.total_trades}")
        if vs_benchmark:
            click.echo(
                f"  CSI 300: {vs_benchmark.benchmark_return_pct:+.2f}% | "
                f"Alpha: {vs_benchmark.alpha:+.2f}%"
            )

    except Exception as e:
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
    source_cassette = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "replays"
        / "momentum_dragon_2024-03-14.jsonl"
    )
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
            mask_entities=True,
            entity_mask_seed=42,
            replay=cassette_path,
            record_replay=None,
        )


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
    from datetime import UTC, date, datetime
    from decimal import Decimal
    from pathlib import Path

    from traderharness import __version__ as th_version
    from traderharness.agents.agent_card import load_card
    from traderharness.agents.llm_client import LLMClient
    from traderharness.agents.prompt_agent import PromptAgent
    from traderharness.agents.tool_agent import ToolAgent
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
    prompt_contract_version = (
        replay_player.manifest.prompt_contract_version if replay_player is not None else None
    )

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
            )
        else:
            card = load_card(spec)
            if not card:
                raise click.ClickException(f"Agent card '{spec}' not found")
            scope = executor_scope_id(card.id, is_committee=False)
            scoped_player = replay_player.scope(scope) if replay_player is not None else None
            scoped_recorder = (
                replay_recorder.scope(scope) if replay_recorder is not None else None
            )
            api_key = (
                "replay" if scoped_player is not None else os.environ.get("DEEPSEEK_API_KEY", "")
            )
            if not api_key:
                raise click.ClickException("DEEPSEEK_API_KEY not set")
            llm = LLMClient(
                model=card.model,
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL", ""),
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
                allowed_tools=card.allowed_tools,
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
        )
    )
    click.echo(
        f"Running {len(agents)} agents: {', '.join(ids)} ({start_date} -> {end_date})"
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
            mask_entities=mask_entities,
            entity_mask_seed=entity_mask_seed,
            agents=[
                AgentManifestEntry(
                    id=agent.agent_id,
                    name=getattr(agent, "name", agent.agent_id),
                    model=getattr(agent.llm_client, "model", ""),
                    cassette=(
                        f"{executor_scope_id(agent.agent_id, is_committee=_is_committee(agent))}"
                        ".jsonl"
                    ),
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
            created_at=datetime.now(UTC).isoformat(),
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
        behavior[agent_id] = (
            entity_masker.mask_obj(metrics) if entity_masker is not None else metrics
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = output or results_dir() / f"{stamp}_comparison.html"
    write_comparison_html(html_path, rows, behavior)
    json_path = Path(html_path).with_suffix(".json")
    agent_runs = {}
    for agent_id, data in engine_result.agent_data.items():
        trades = data["trades"]
        if entity_masker is not None:
            trades = entity_masker.mask_obj(trades)
        agent_runs[agent_id] = {
            "equity_curve": [(str(day), float(value)) for day, value in data["equity_curve"]],
            "trades": trades,
            "trajectory": data.get("trajectory"),
        }
    json_path.write_text(
        json.dumps(
            {
                "start_date": start,
                "end_date": end,
                "mask_entities": mask_entities,
                "entity_mask_seed": entity_mask_seed,
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
            raise click.ClickException(
                f"Recorded replay bundle failed leakage audit "
                f"({audit_report['finding_count']} findings); "
                f"comparison was still written to {html_path}"
            )
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
    default="daily,5min,valuation,announcements,news,benchmark",
    help="Comma-separated: daily,5min,valuation,announcements,news,benchmark",
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
        BaostockValuationProvider,
        ClsNewsProvider,
        CninfoAnnouncementsProvider,
    )
    from traderharness.data.updater import DataUpdater, UpdatePlan
    from traderharness.paths import dataset_dir

    selected = {item.strip() for item in only.split(",") if item.strip()}
    updater = DataUpdater(
        dataset_dir(),
        daily_provider=BaostockDailyProvider(),
        min5_provider=Baostock5MinProvider(),
        valuation_provider=BaostockValuationProvider(),
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
            click.echo(
                f"{name}: rows {value.rows_before:,} -> {value.rows_after:,} "
                f"(+{value.rows_added:,})"
            )


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
