"""CLI entry point — traderharness run/data/benchmark/ui."""

from __future__ import annotations

import click
from dotenv import load_dotenv
load_dotenv()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """TraderHarness — LLM-native trading agent harness."""
    pass


@main.command()
@click.option("--agent", "-a", required=True, help="Agent card ID or YAML config path")
@click.option("--start", "-s", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", required=True, help="End date (YYYY-MM-DD)")
@click.option("--model", "-m", default=None, help="Override model (deepseek-chat, deepseek-v4-flash)")
@click.option("--cash", default=1000000, help="Initial cash (default: 1000000)")
def run(agent: str, start: str, end: str, model: str | None, cash: int):
    """Run a backtest with the specified agent card."""
    import asyncio
    import os
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from traderharness.results import generate_result_filename, save_pending, save_complete, save_failed, RESULTS_DIR

    # Resolve agent
    agent_path = Path(agent)
    if agent_path.exists() and agent_path.suffix in (".yaml", ".yml"):
        from traderharness.agents.prompt_agent import PromptAgent
        from traderharness.agents.llm_client import LLMClient

        agent_obj = PromptAgent(agent_path)
        agent_id = agent_obj.agent_id
        click.echo(f"Agent (YAML): {agent_obj.name}")
    else:
        from traderharness.agents.agent_card import load_card
        from traderharness.agents.tool_agent import ToolAgent
        from traderharness.agents.llm_client import LLMClient

        card = load_card(agent)
        if not card:
            click.echo(f"Error: Agent card '{agent}' not found.", err=True)
            click.echo("Available cards:", err=True)
            from traderharness.agents.agent_card import list_cards
            for c in list_cards():
                click.echo(f"  {c.id} -- {c.name}", err=True)
            raise SystemExit(1)

        use_model = model or card.model
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "")

        if not api_key:
            click.echo("Error: DEEPSEEK_API_KEY not set.", err=True)
            raise SystemExit(1)

        llm = LLMClient(model=use_model, api_key=api_key, base_url=base_url, cache_enabled=False)
        agent_obj = ToolAgent(
            agent_id=card.id, name=card.name,
            llm_client=llm, persona=card.persona,
            initial_cash=Decimal(str(cash)),
            max_positions=card.max_positions,
            max_position_pct=card.max_position_pct,
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
        "model": model or "deepseek-chat",
        "agent_id": agent_id,
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
        from traderharness.core.engine import BacktestEngine, EngineConfig
        from traderharness.core.events import EventBus
        from traderharness.metrics.performance import calculate_metrics

        engine = BacktestEngine(EngineConfig(initial_cash=initial_cash), event_bus=EventBus())
        result = asyncio.run(engine.run([agent_obj], start_date, end_date))

        data = result.agent_data[agent_id]
        metrics = calculate_metrics(data["equity_curve"], initial_cash, data["trades"])

        result_data = {
            "trading_days": result.trading_days,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "config": config,
            "agent_data": {
                agent_id: {
                    "equity_curve": [(str(d), float(v)) for d, v in data["equity_curve"]],
                    "trades": data["trades"],
                    "trajectory": data.get("trajectory"),
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
        }

        save_complete(result_filename, result_data)

        # Clean up live file
        if live_file.exists():
            live_file.unlink()

        click.echo(f"\nDone! {result.trading_days} trading days")
        click.echo(f"  Return: {metrics.total_return_pct:+.2f}%")
        click.echo(f"  Sharpe: {metrics.sharpe_ratio:.2f}")
        click.echo(f"  Max DD: -{metrics.max_drawdown_pct:.2f}%")
        click.echo(f"  Trades: {metrics.total_trades}")

    except Exception as e:
        save_failed(result_filename, str(e), config)
        if live_file.exists():
            live_file.unlink()
        click.echo(f"\nFailed: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise SystemExit(1)


@main.command()
@click.argument("action", type=click.Choice(["download", "list"]))
@click.option("--dataset", "-d", default=None, help="Dataset name")
def data(action: str, dataset: str | None):
    """Manage datasets (download, list)."""
    from traderharness.data.datasets import list_datasets, ensure_dataset

    if action == "list":
        datasets = list_datasets()
        click.echo("Available datasets:")
        for ds in datasets:
            status = "[x]" if ds["downloaded"] else "[ ]"
            click.echo(f"  {status} {ds['name']} — {ds['description']}")
    elif action == "download":
        if not dataset:
            click.echo("Error: --dataset required for download", err=True)
            return
        click.echo(f"Downloading {dataset}...")
        path = ensure_dataset(dataset)
        click.echo(f"Downloaded to: {path}")


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
@click.option("--port", "-p", default=8501, help="Streamlit port")
def ui(port: int):
    """Launch Streamlit web UI."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent / "ui" / "app.py"
    if not app_path.exists():
        click.echo("Error: UI module not found", err=True)
        return
    click.echo(f"Starting TraderHarness UI on port {port}...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
    )


if __name__ == "__main__":
    main()
