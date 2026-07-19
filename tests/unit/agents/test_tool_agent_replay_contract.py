"""DECISION_RECORDING_CONTRACT injection must stay fingerprint-stable across
record/replay, driven by an explicit `prompt_contract_version` (as read from a
Replay Bundle manifest) when available, and falling back to the legacy
`_player`-presence heuristic for v1 single-file cassettes that predate the
contract feature.
"""

from decimal import Decimal

from traderharness.agents.tool_agent import (
    CONTRACT_VERSION,
    DECISION_RECORDING_CONTRACT,
    LEGACY_CONTRACT_VERSION,
    ToolAgent,
    resolve_decision_contract,
)


class _StubLLM:
    model = "stub"
    _player = None


class _StubReplayingLLM:
    model = "stub"
    _player = object()


def _make_agent(tmp_path, llm_client, **kwargs) -> ToolAgent:
    return ToolAgent(
        agent_id="contract_test",
        name="contract_test",
        llm_client=llm_client,
        initial_cash=Decimal("1000000"),
        memory_dir=str(tmp_path),
        **kwargs,
    )


class TestResolveDecisionContract:
    def test_live_client_without_player_injects_contract_and_reports_current_version(self):
        text, version = resolve_decision_contract(_StubLLM())
        assert text == DECISION_RECORDING_CONTRACT
        assert version == CONTRACT_VERSION

    def test_legacy_replay_without_manifest_suppresses_contract(self):
        text, version = resolve_decision_contract(_StubReplayingLLM())
        assert text != DECISION_RECORDING_CONTRACT
        assert version == LEGACY_CONTRACT_VERSION

    def test_manifest_says_current_version_forces_injection_even_while_replaying(self):
        text, version = resolve_decision_contract(
            _StubReplayingLLM(), prompt_contract_version=CONTRACT_VERSION
        )
        assert text == DECISION_RECORDING_CONTRACT
        assert version == CONTRACT_VERSION

    def test_manifest_says_legacy_version_suppresses_even_on_live_client(self):
        text, version = resolve_decision_contract(
            _StubLLM(), prompt_contract_version=LEGACY_CONTRACT_VERSION
        )
        assert text != DECISION_RECORDING_CONTRACT
        assert version == LEGACY_CONTRACT_VERSION


class TestToolAgentContractWiring:
    def test_live_agent_injects_contract_by_default(self, tmp_path):
        agent = _make_agent(tmp_path, _StubLLM())
        assert "决策记录要求" in agent._system_prompt
        assert agent.prompt_contract_version == CONTRACT_VERSION

    def test_legacy_replay_agent_suppresses_contract(self, tmp_path):
        agent = _make_agent(tmp_path, _StubReplayingLLM())
        assert "决策记录要求" not in agent._system_prompt
        assert agent.prompt_contract_version == LEGACY_CONTRACT_VERSION

    def test_explicit_prompt_contract_version_overrides_player_heuristic(self, tmp_path):
        agent = _make_agent(
            tmp_path,
            _StubReplayingLLM(),
            prompt_contract_version=CONTRACT_VERSION,
        )
        assert "决策记录要求" in agent._system_prompt
        assert agent.prompt_contract_version == CONTRACT_VERSION

    def test_compare_replay_must_pass_manifest_contract_version(self, tmp_path):
        """Regression: bundle replay with a player but no explicit version used to
        suppress the v2 contract and break request fingerprints at LLM call 0."""
        from traderharness.agents.tool_agent import resolve_decision_contract

        # Mimic compare CLI: ScopedReplayPlayer present + manifest says v2.
        text, version = resolve_decision_contract(
            _StubReplayingLLM(), prompt_contract_version="v2"
        )
        assert version == CONTRACT_VERSION
        assert text == DECISION_RECORDING_CONTRACT
        agent = _make_agent(
            tmp_path,
            _StubReplayingLLM(),
            prompt_contract_version="v2",
        )
        assert "决策记录要求" in agent._system_prompt
