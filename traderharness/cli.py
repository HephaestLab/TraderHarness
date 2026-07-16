"""CLI entry point — finharness run/data/benchmark/ui."""

from __future__ import annotations

import click


@click.group()
@click.version_option(version="0.1.0")
def main():
    """FinHarness — LLM-native trading agent harness."""
    pass


@main.command()
@click.option("--agent", "-a", required=True, help="Agent YAML config path")
@click.option("--config", "-c", default=None, help="Environment config YAML path")
@click.option("--dataset", "-d", default=None, help="Dataset name (e.g., a50-2024)")
@click.option("--output", "-o", default="./runs", help="Output directory")
def run(agent: str, config: str | None, dataset: str | None, output: str):
    """Run a backtest with the specified agent."""
    from pathlib import Path
    from finharness.config.env_config import AgentYAMLConfig, EnvYAMLConfig

    agent_cfg = AgentYAMLConfig.from_yaml(agent)
    click.echo(f"Agent: {agent_cfg.name} (model: {agent_cfg.model})")

    if config:
        env_cfg = EnvYAMLConfig.from_yaml(config)
        click.echo(f"Config: {env_cfg.backtest.start} → {env_cfg.backtest.end}")
    else:
        click.echo("Using default config")

    click.echo(f"Output: {output}")
    click.echo("Running backtest...")
    # Actual backtest execution would go here
    click.echo("Done.")


@main.command()
@click.argument("action", type=click.Choice(["download", "list"]))
@click.option("--dataset", "-d", default=None, help="Dataset name")
def data(action: str, dataset: str | None):
    """Manage datasets (download, list)."""
    from finharness.data.datasets import list_datasets, ensure_dataset

    if action == "list":
        datasets = list_datasets()
        click.echo("Available datasets:")
        for ds in datasets:
            status = "✓" if ds["downloaded"] else "✗"
            click.echo(f"  [{status}] {ds['name']} — {ds['description']}")
    elif action == "download":
        if not dataset:
            click.echo("Error: --dataset required for download", err=True)
            return
        click.echo(f"Downloading {dataset}...")
        path = ensure_dataset(dataset)
        click.echo(f"Downloaded to: {path}")


@main.command()
@click.option("--agent", "-a", required=True, help="Agent YAML config path")
@click.option("--dataset", "-d", default="test-fixture", help="Dataset name")
@click.option("--runs", "-n", default=1, help="Number of runs for statistical analysis")
def benchmark(agent: str, dataset: str, runs: int):
    """Run benchmark with optional multi-run statistics."""
    click.echo(f"Benchmarking: {agent}")
    click.echo(f"Dataset: {dataset}")
    click.echo(f"Runs: {runs}")

    if runs > 1:
        click.echo(f"\nResults ({runs} runs):")
        click.echo("  Return:   +X.X% ± X.X%")
        click.echo("  Sharpe:   X.XX ± X.XX")
        click.echo("  DrawDown: -X.X% ± X.X%")
    else:
        click.echo("\nRunning single benchmark...")
    click.echo("Done.")


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
    click.echo(f"Starting FinHarness UI on port {port}...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
    )


if __name__ == "__main__":
    main()
