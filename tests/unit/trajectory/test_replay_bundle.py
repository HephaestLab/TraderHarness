"""Tests for Replay Bundle v2 — multi-agent scoped recording and playback."""

from datetime import date

import pytest

from traderharness.trajectory.bundle import (
    MANIFEST_SCHEMA_VERSION,
    AgentManifestEntry,
    ReplayBundleManifest,
    ScopedReplayPlayer,
    ScopedReplayRecorder,
    advisor_scope_id,
    executor_scope_id,
    is_bundle_path,
)
from traderharness.trajectory.replay import (
    ReplayExhaustedError,
    ReplayMismatchError,
    ReplayPlayer,
    ReplayRecorder,
    request_fingerprint,
)


class TestScopeHelpers:
    def test_executor_scope_is_bare_agent_id_when_not_committee(self):
        assert executor_scope_id("trend-breakout") == "trend-breakout"
        assert executor_scope_id("trend-breakout", is_committee=False) == "trend-breakout"

    def test_executor_scope_is_suffixed_for_committees(self):
        assert executor_scope_id("committee-id", is_committee=True) == "committee-id__executor"

    def test_advisor_scope_is_namespaced_under_agent(self):
        assert (
            advisor_scope_id("committee-id", "fundamentals")
            == "committee-id__advisor_fundamentals"
        )

    def test_is_bundle_path_detects_existing_directory(self, tmp_path):
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        assert is_bundle_path(bundle_dir) is True

    def test_is_bundle_path_detects_existing_jsonl_file(self, tmp_path):
        cassette = tmp_path / "cassette.jsonl"
        cassette.write_text("", encoding="utf-8")
        assert is_bundle_path(cassette) is False

    def test_is_bundle_path_infers_from_suffix_when_missing(self, tmp_path):
        assert is_bundle_path(tmp_path / "new_bundle") is True
        assert is_bundle_path(tmp_path / "new_cassette.jsonl") is False


class TestReplayBundleManifest:
    def test_round_trips_through_json(self, tmp_path):
        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
            initial_cash=1_000_000.0,
            mask_entities=True,
            entity_mask_seed=7,
            agents=[
                AgentManifestEntry(
                    id="trend-breakout",
                    name="Trend Breakout",
                    model="deepseek-chat",
                    cassette="trend-breakout.jsonl",
                ),
            ],
            prompt_contract_version="v2",
            thinking={"enabled": True, "effort": "high"},
            created_at="2024-03-04T00:00:00+00:00",
            traderharness_version="1.0.0",
        )
        path = tmp_path / "manifest.json"
        manifest.save(path)

        loaded = ReplayBundleManifest.load(path)

        assert loaded.schema_version == MANIFEST_SCHEMA_VERSION
        assert loaded.start_date == date(2024, 3, 4)
        assert loaded.end_date == date(2024, 3, 5)
        assert loaded.entity_mask_seed == 7
        assert loaded.prompt_contract_version == "v2"
        assert loaded.thinking == {"enabled": True, "effort": "high"}
        assert loaded.agents[0] == AgentManifestEntry(
            id="trend-breakout",
            name="Trend Breakout",
            model="deepseek-chat",
            cassette="trend-breakout.jsonl",
        )

    def test_agent_by_id_looks_up_manifest_entry(self):
        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[AgentManifestEntry(id="a"), AgentManifestEntry(id="b")],
        )

        assert manifest.agent_by_id("b").id == "b"
        assert manifest.agent_by_id("missing") is None


class TestScopedReplayRecorderAndPlayer:
    def test_two_agents_concurrent_record_to_independent_cassettes(self, tmp_path):
        recorder = ScopedReplayRecorder()
        trend_handle = recorder.scope("trend-breakout")
        quality_handle = recorder.scope("quality-compounder")

        trend_handle.record_llm_call(
            messages=[{"role": "user", "content": "trend prompt day1"}],
            tools=None,
            output={"role": "assistant", "content": "trend response day1"},
        )
        quality_handle.record_llm_call(
            messages=[{"role": "user", "content": "quality prompt day1"}],
            tools=None,
            output={"role": "assistant", "content": "quality response day1"},
        )
        trend_handle.record_llm_call(
            messages=[{"role": "user", "content": "trend prompt day2"}],
            tools=None,
            output={"role": "assistant", "content": "trend response day2"},
        )

        assert sorted(recorder.scope_ids) == ["quality-compounder", "trend-breakout"]
        assert len(trend_handle.entries) == 2
        assert len(quality_handle.entries) == 1

        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 5),
            agents=[
                AgentManifestEntry(id="trend-breakout", cassette="trend-breakout.jsonl"),
                AgentManifestEntry(id="quality-compounder", cassette="quality-compounder.jsonl"),
            ],
        )
        bundle_dir = tmp_path / "bundle"
        manifest_path = recorder.save_bundle(bundle_dir, manifest)

        assert manifest_path == bundle_dir / "manifest.json"
        assert (bundle_dir / "agents" / "trend-breakout.jsonl").exists()
        assert (bundle_dir / "agents" / "quality-compounder.jsonl").exists()

        # Replay each agent's cassette independently and verify fingerprints match.
        player = ScopedReplayPlayer(bundle_dir)
        trend_player = player.scope("trend-breakout")
        quality_player = player.scope("quality-compounder")

        assert trend_player.total_entries == 2
        assert quality_player.total_entries == 1

        first = trend_player.require_response(
            messages=[{"role": "user", "content": "trend prompt day1"}], tools=None
        )
        assert first["content"] == "trend response day1"
        second = trend_player.require_response(
            messages=[{"role": "user", "content": "trend prompt day2"}], tools=None
        )
        assert second["content"] == "trend response day2"

        quality_response = quality_player.require_response(
            messages=[{"role": "user", "content": "quality prompt day1"}], tools=None
        )
        assert quality_response["content"] == "quality response day1"

        player.assert_all_consumed()

    def test_replay_mismatch_raised_when_request_diverges(self, tmp_path):
        recorder = ScopedReplayRecorder()
        recorder.scope("agent-a").record_llm_call(
            messages=[{"role": "user", "content": "original"}],
            tools=None,
            output={"role": "assistant", "content": "ok"},
        )
        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[AgentManifestEntry(id="agent-a", cassette="agent-a.jsonl")],
        )
        bundle_dir = tmp_path / "bundle"
        recorder.save_bundle(bundle_dir, manifest)

        player = ScopedReplayPlayer(bundle_dir)
        with pytest.raises(ReplayMismatchError):
            player.scope("agent-a").require_response(
                messages=[{"role": "user", "content": "different"}], tools=None
            )

    def test_missing_scope_cassette_raises_file_not_found(self, tmp_path):
        recorder = ScopedReplayRecorder()
        recorder.scope("agent-a").record_llm_call(
            messages=[], tools=None, output={"role": "assistant", "content": "ok"}
        )
        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[AgentManifestEntry(id="agent-a", cassette="agent-a.jsonl")],
        )
        bundle_dir = tmp_path / "bundle"
        recorder.save_bundle(bundle_dir, manifest)

        player = ScopedReplayPlayer(bundle_dir)
        with pytest.raises(FileNotFoundError):
            player.scope("agent-b")

    def test_scoped_player_requires_manifest(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ScopedReplayPlayer(tmp_path / "does-not-exist")

    def test_committee_advisor_and_executor_scopes_stay_independent(self, tmp_path):
        recorder = ScopedReplayRecorder()
        executor_scope = executor_scope_id("committee-1", is_committee=True)
        advisor_scope = advisor_scope_id("committee-1", "fundamentals")

        recorder.scope(executor_scope).record_llm_call(
            messages=[{"role": "user", "content": "exec"}],
            tools=[{"type": "function", "function": {"name": "place_order"}}],
            output={"role": "assistant", "content": "buy"},
        )
        recorder.scope(advisor_scope).record_llm_call(
            messages=[{"role": "user", "content": "advise"}],
            tools=None,
            output={"role": "assistant", "content": "看多"},
        )

        manifest = ReplayBundleManifest(
            start_date=date(2024, 3, 4),
            end_date=date(2024, 3, 4),
            agents=[
                AgentManifestEntry(
                    id="committee-1",
                    cassette=f"{executor_scope}.jsonl",
                ),
            ],
        )
        bundle_dir = tmp_path / "bundle"
        recorder.save_bundle(bundle_dir, manifest)

        assert (bundle_dir / "agents" / f"{executor_scope}.jsonl").exists()
        assert (bundle_dir / "agents" / f"{advisor_scope}.jsonl").exists()

        player = ScopedReplayPlayer(bundle_dir)
        exec_response = player.scope(executor_scope).require_response(
            messages=[{"role": "user", "content": "exec"}],
            tools=[{"type": "function", "function": {"name": "place_order"}}],
        )
        advisor_response = player.scope(advisor_scope).require_response(
            messages=[{"role": "user", "content": "advise"}], tools=None
        )
        assert exec_response["content"] == "buy"
        assert advisor_response["content"] == "看多"


class TestV1SingleFileCompatibility:
    """Bundle v2 additions must not disturb the existing single-file cassette contract."""

    def test_v1_recorder_and_player_untouched(self, tmp_path):
        path = tmp_path / "legacy.jsonl"
        rec = ReplayRecorder()
        rec.record_llm_call(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            output={"role": "assistant", "content": "hello"},
        )
        rec.save(path)

        player = ReplayPlayer(path)
        response = player.require_response(
            messages=[{"role": "user", "content": "hi"}], tools=None
        )
        assert response["content"] == "hello"
        player.assert_consumed()

    def test_v1_player_still_raises_on_exhaustion(self, tmp_path):
        path = tmp_path / "legacy_empty.jsonl"
        ReplayRecorder().save(path)
        player = ReplayPlayer(path)
        with pytest.raises(ReplayExhaustedError):
            player.require_response(messages=[], tools=None)

    def test_scoped_recorder_view_produces_same_fingerprint_as_plain_recorder(self):
        messages = [{"role": "user", "content": "same request"}]
        tools = [{"type": "function", "function": {"name": "finish_day"}}]

        scoped = ScopedReplayRecorder()
        scoped.scope("agent").record_llm_call(
            messages=messages, tools=tools, output={"content": "x"}
        )
        plain_entry = scoped.recorder_for("agent").entries[0]

        assert plain_entry["request_sha256"] == request_fingerprint(messages, tools)
