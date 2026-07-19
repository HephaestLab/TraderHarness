"""BacktestRunner agent construction — v1 single-file replay stays limited to
one executor agent; a Replay Bundle directory unlocks multi-agent replay,
matching each agent's cassette to its own agent id.
"""

from datetime import date

import pytest

from traderharness.core.runner import BacktestRunner, RunConfig
from traderharness.trajectory.bundle import (
    AgentManifestEntry,
    ReplayBundleManifest,
    ScopedReplayRecorder,
)


def _make_bundle(tmp_path, agent_ids: list[str]) -> "Path":  # noqa: F821
    recorder = ScopedReplayRecorder()
    for agent_id in agent_ids:
        recorder.scope(agent_id).record_llm_call(
            messages=[{"role": "user", "content": f"{agent_id} prompt"}],
            tools=None,
            output={"role": "assistant", "content": f"{agent_id} response"},
        )
    manifest = ReplayBundleManifest(
        start_date=date(2024, 3, 4),
        end_date=date(2024, 3, 4),
        agents=[AgentManifestEntry(id=agent_id) for agent_id in agent_ids],
    )
    bundle_dir = tmp_path / "bundle"
    recorder.save_bundle(bundle_dir, manifest)
    return bundle_dir


class TestBundleMultiAgentReplay:
    def test_bundle_directory_builds_one_agent_per_config_scoped_by_id(self, tmp_path):
        bundle_dir = _make_bundle(tmp_path, ["trend-breakout", "quality-compounder"])
        config = RunConfig(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[
                {"id": "trend-breakout", "name": "Trend Breakout"},
                {"id": "quality-compounder", "name": "Quality Compounder"},
            ],
            replay_path=bundle_dir,
        )
        runner = BacktestRunner(config)

        agents = runner._build_agents()

        assert {a.agent_id for a in agents} == {"trend-breakout", "quality-compounder"}
        for agent in agents:
            assert agent.llm_client._player is not None

    def test_single_file_cassette_still_limited_to_one_agent(self, tmp_path):
        from traderharness.trajectory.replay import ReplayRecorder

        cassette = tmp_path / "legacy.jsonl"
        ReplayRecorder().save(cassette)
        config = RunConfig(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[{"id": "a"}, {"id": "b"}],
            replay_path=cassette,
        )
        runner = BacktestRunner(config)

        with pytest.raises(ValueError, match="exactly one"):
            runner._build_agents()

    def test_replay_propagates_prompt_contract_version_to_agents(self, tmp_path):
        """Regression: the server/demo path built ToolAgents without the
        cassette's prompt_contract_version, so a v2-recorded cassette fell
        back to the legacy player heuristic (contract suppressed) and every
        replay through the Web UI mismatched at LLM call 0."""
        from traderharness.agents.tool_agent import CONTRACT_VERSION
        from traderharness.trajectory.replay import ReplayRecorder

        cassette = tmp_path / "v2.jsonl"
        ReplayRecorder(prompt_contract_version=CONTRACT_VERSION).save(cassette)
        config = RunConfig(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[{"id": "momentum-dragon"}],
            replay_path=cassette,
        )

        agents = BacktestRunner(config)._build_agents()

        assert agents[0].prompt_contract_version == CONTRACT_VERSION

    def test_bundle_replay_propagates_manifest_contract_version(self, tmp_path):
        from traderharness.agents.tool_agent import CONTRACT_VERSION

        recorder = ScopedReplayRecorder()
        recorder.scope("trend-breakout").record_llm_call(
            messages=[{"role": "user", "content": "prompt"}],
            tools=None,
            output={"role": "assistant", "content": "response"},
        )
        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[AgentManifestEntry(id="trend-breakout")],
            prompt_contract_version=CONTRACT_VERSION,
        )
        bundle_dir = tmp_path / "bundle"
        recorder.save_bundle(bundle_dir, manifest)
        config = RunConfig(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[{"id": "trend-breakout"}],
            replay_path=bundle_dir,
        )

        agents = BacktestRunner(config)._build_agents()

        assert agents[0].prompt_contract_version == CONTRACT_VERSION

    def test_bundle_missing_agent_scope_raises_file_not_found(self, tmp_path):
        bundle_dir = _make_bundle(tmp_path, ["trend-breakout"])
        config = RunConfig(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[{"id": "trend-breakout"}, {"id": "unknown-agent"}],
            replay_path=bundle_dir,
        )
        runner = BacktestRunner(config)

        with pytest.raises(FileNotFoundError):
            runner._build_agents()
