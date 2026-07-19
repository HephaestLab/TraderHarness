"""CLI surface contracts."""

import json

from click.testing import CliRunner

from traderharness import __version__
from traderharness.cli import main


def test_cli_version_reflects_package_version_not_hardcoded():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
    # Guard against regressing to the old hardcoded "0.1.0".
    if __version__ != "0.1.0":
        assert "0.1.0" not in result.output


def test_run_persists_resolved_model_not_hardcoded_default(monkeypatch, tmp_path):
    """The persisted run config must reflect the agent's actual model.

    momentum-dragon's card model is deepseek-v4-pro; if the CLI hardcodes
    "deepseek-chat" as the persisted default, this assertion catches it.
    """
    from traderharness.core.engine import BacktestEngine

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("traderharness.results.RESULTS_DIR", tmp_path)

    async def _boom(self, *args, **kwargs):
        raise RuntimeError("stop-before-backtest")

    monkeypatch.setattr(BacktestEngine, "run", _boom)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--agent",
            "momentum-dragon",
            "--start",
            "2024-03-14",
            "--end",
            "2024-03-14",
        ],
    )

    assert result.exit_code == 1
    saved_files = list(tmp_path.glob("*_result.json"))
    assert len(saved_files) == 1
    saved = json.loads(saved_files[0].read_text(encoding="utf-8"))
    assert saved["config"]["model"] == "deepseek-v4-pro"
    assert saved["config"]["model"] != "deepseek-chat"


def test_run_exposes_entity_masking_controls():
    result = CliRunner().invoke(main, ["run", "--help"])

    assert result.exit_code == 0
    assert "--mask-entities" in result.output
    assert "--no-mask-entities" in result.output
    assert "--entity-mask-seed" in result.output
    assert "--replay" in result.output
    assert "--record-replay" in result.output


def test_cli_exposes_artifact_audit_command():
    result = CliRunner().invoke(main, ["audit", "--help"])

    assert result.exit_code == 0
    assert "ARTIFACTS" in result.output
    assert "--json-output" in result.output


def test_cli_exposes_no_key_demo_command():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "demo" in result.output
    assert "without an API key" in result.output


def test_cli_exposes_sft_export_command():
    result = CliRunner().invoke(main, ["export", "sft", "--help"])

    assert result.exit_code == 0
    assert "--output" in result.output
    assert "--allow-unmasked" in result.output


def test_ui_defaults_to_localhost_and_requires_explicit_public_opt_in():
    help_result = CliRunner().invoke(main, ["ui", "--help"])
    assert help_result.exit_code == 0
    assert "--host" in help_result.output
    assert "--allow-public" in help_result.output

    rejected = CliRunner().invoke(main, ["ui", "--host", "0.0.0.0"])
    assert rejected.exit_code == 2
    assert "local-only" in rejected.output


def test_run_rejects_simultaneous_record_and_replay(tmp_path):
    cassette = tmp_path / "demo.jsonl"
    cassette.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--agent",
            "unused",
            "--start",
            "2024-03-04",
            "--end",
            "2024-03-04",
            "--replay",
            str(cassette),
            "--record-replay",
            str(tmp_path / "new.jsonl"),
        ],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_data_exposes_incremental_update_command():
    result = CliRunner().invoke(main, ["data", "--help"])

    assert result.exit_code == 0
    assert "update" in result.output
    assert "download" in result.output
    assert "list" in result.output

    download_help = CliRunner().invoke(main, ["data", "download", "--help"])
    assert download_help.exit_code == 0
    assert "--full" in download_help.output
    assert "--force" in download_help.output

    update_help = CliRunner().invoke(main, ["data", "update", "--help"])
    assert update_help.exit_code == 0
    assert "valuation" in update_help.output


def test_compare_exposes_repeatable_agents_and_entity_masking():
    result = CliRunner().invoke(main, ["compare", "--help"])

    assert result.exit_code == 0
    assert "--agent" in result.output
    assert "--mask-entities" in result.output
    assert "--output" in result.output
    assert "--replay" in result.output
    assert "--record-replay" in result.output


def test_compare_rejects_simultaneous_record_and_replay(tmp_path):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    result = CliRunner().invoke(
        main,
        [
            "compare",
            "--agent",
            "unused-a",
            "--agent",
            "unused-b",
            "--start",
            "2024-03-04",
            "--end",
            "2024-03-04",
            "--replay",
            str(bundle_dir),
            "--record-replay",
            str(tmp_path / "new_bundle"),
        ],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_compare_replay_requires_a_bundle_directory_not_a_single_cassette(tmp_path):
    cassette = tmp_path / "legacy.jsonl"
    cassette.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "compare",
            "--agent",
            "unused-a",
            "--agent",
            "unused-b",
            "--start",
            "2024-03-04",
            "--end",
            "2024-03-04",
            "--replay",
            str(cassette),
        ],
    )

    assert result.exit_code == 2
    assert "Replay Bundle directory" in result.output


def test_run_replay_accepts_a_bundle_directory():
    result = CliRunner().invoke(main, ["run", "--help"])

    assert result.exit_code == 0
    assert "Replay Bundle" in result.output


def test_compare_reports_agent_execution_error_without_a_raw_traceback(monkeypatch):
    """compare must fail closed with a readable message, not an unhandled traceback.

    ``BacktestEngine.run`` raises ``AgentExecutionError`` (not a bare exception) when
    one or more agents fail, precisely so callers can report which agent failed and
    why. The CLI previously let this propagate uncaught.
    """
    from traderharness.core.engine import AgentExecutionError, BacktestEngine, EngineResult

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    async def _boom(self, agents, start_date, end_date, **kwargs):
        result = EngineResult(trading_days=0, start_date=start_date, end_date=end_date)
        result.failed_agents["momentum-dragon"] = "RuntimeError: sandbox timeout"
        raise AgentExecutionError(
            "1 agent(s) failed during backtest; "
            "first failure (momentum-dragon): RuntimeError: sandbox timeout",
            result=result,
        )

    monkeypatch.setattr(BacktestEngine, "run", _boom)

    result = CliRunner().invoke(
        main,
        [
            "compare",
            "--agent",
            "momentum-dragon",
            "--agent",
            "value-sage",
            "--start",
            "2024-03-14",
            "--end",
            "2024-03-14",
        ],
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "momentum-dragon" in result.output
    assert "sandbox timeout" in result.output
