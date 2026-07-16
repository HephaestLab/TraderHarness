"""Tests for Replay mode."""

from datetime import date

import pytest

from traderharness.trajectory.replay import ReplayRecorder, ReplayPlayer


class TestReplayRecorder:
    def test_record_and_save(self, tmp_path):
        rec = ReplayRecorder()
        rec.record(date(2024, 3, 4), 0, "llm_call", {"input": "hi", "output": "hello"})
        rec.record(date(2024, 3, 4), 1, "tool_call", {"name": "get_kline"})
        path = tmp_path / "replay.jsonl"
        rec.save(path)
        assert path.exists()
        assert len(rec) == 2

    def test_entries_property(self):
        rec = ReplayRecorder()
        rec.record(date(2024, 3, 4), 0, "llm_call", {"data": "test"})
        entries = rec.entries
        assert len(entries) == 1
        assert entries[0]["type"] == "llm_call"


class TestReplayPlayer:
    def test_load_and_replay(self, tmp_path):
        path = tmp_path / "replay.jsonl"
        rec = ReplayRecorder()
        rec.record(date(2024, 3, 4), 0, "llm_call", {"output": "response1"})
        rec.record(date(2024, 3, 4), 1, "llm_call", {"output": "response2"})
        rec.save(path)

        player = ReplayPlayer(path)
        assert player.total_entries == 2
        r1 = player.next_response()
        assert r1["output"] == "response1"
        r2 = player.next_response()
        assert r2["output"] == "response2"
        assert player.next_response() is None

    def test_get_for_date(self, tmp_path):
        path = tmp_path / "replay.jsonl"
        rec = ReplayRecorder()
        rec.record(date(2024, 3, 4), 0, "llm_call", {"data": "day1"})
        rec.record(date(2024, 3, 5), 0, "llm_call", {"data": "day2"})
        rec.save(path)

        player = ReplayPlayer(path)
        day1 = player.get_for_date(date(2024, 3, 4))
        assert len(day1) == 1
        assert day1[0]["data"] == "day1"

    def test_reset(self, tmp_path):
        path = tmp_path / "replay.jsonl"
        rec = ReplayRecorder()
        rec.record(date(2024, 3, 4), 0, "llm_call", {"data": "x"})
        rec.save(path)

        player = ReplayPlayer(path)
        player.next_response()
        player.reset()
        assert player.next_response() is not None

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            ReplayPlayer("/nonexistent.jsonl")
