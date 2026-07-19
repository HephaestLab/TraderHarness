"""Integration test — replay mode."""

from datetime import date

from traderharness.trajectory.replay import ReplayPlayer, ReplayRecorder


class TestReplayMode:
    def test_record_and_replay_deterministic(self, tmp_path):
        """Record LLM responses, replay and get same sequence."""
        recorder = ReplayRecorder()
        recorder.record(
            date(2024, 3, 4),
            0,
            "llm_call",
            {
                "input": [{"role": "user", "content": "analyze"}],
                "output": {"content": "Market looks bullish"},
            },
        )
        recorder.record(
            date(2024, 3, 4),
            1,
            "tool_call",
            {
                "name": "get_kline",
                "args": {"code": "600519"},
                "result": {"close": 1800},
            },
        )
        recorder.record(
            date(2024, 3, 5),
            0,
            "llm_call",
            {
                "input": [{"role": "user", "content": "new day"}],
                "output": {"content": "Holding positions"},
            },
        )

        path = tmp_path / "replay.jsonl"
        recorder.save(path)

        player = ReplayPlayer(path)
        assert player.total_entries == 2

        # Replay same sequence
        r1 = player.next_response()
        assert r1["type"] == "llm_call"
        assert r1["output"]["content"] == "Market looks bullish"

        r2 = player.next_response()
        assert r2["type"] == "llm_call"
        assert r2["output"]["content"] == "Holding positions"

        # Filter by date
        day2 = player.get_for_date(date(2024, 3, 5))
        assert len(day2) == 1
        assert day2[0]["output"]["content"] == "Holding positions"
