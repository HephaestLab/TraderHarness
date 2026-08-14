"""Tests for TrajectoryCollector."""

import json
from datetime import date

from traderharness.trajectory.collector import TrajectoryCollector


class TestTrajectoryCollector:
    def test_start_and_end_day(self):
        tc = TrajectoryCollector("test_agent")
        tc.start_day(date(2024, 3, 4), {"cash": 1000000})
        tc.end_day(actions=[{"action": "buy"}], reward=0.05)
        assert len(tc.day_records) == 1
        assert tc.day_records[0].reward == 0.05

    def test_record_steps(self):
        tc = TrajectoryCollector("test_agent")
        tc.start_day(date(2024, 3, 4), {})
        tc.record_step(date(2024, 3, 4), "tool_call", {"name": "get_kline"})
        tc.record_step(date(2024, 3, 4), "llm_call", {"content": "analyzing..."})
        assert len(tc.step_records) == 2
        assert tc.step_records[0].step == 0
        assert tc.step_records[1].step == 1

    def test_to_day_dataframe(self):
        tc = TrajectoryCollector("test_agent")
        tc.start_day(date(2024, 3, 4), {"cash": 1000000})
        tc.end_day(actions=[], reward=0.0)
        df = tc.to_day_dataframe()
        assert len(df) == 1
        assert "reward" in df.columns

    def test_to_step_dataframe(self):
        tc = TrajectoryCollector("test_agent")
        tc.start_day(date(2024, 3, 4), {})
        tc.record_step(date(2024, 3, 4), "tool_call", {"name": "buy"})
        df = tc.to_step_dataframe()
        assert len(df) == 1
        assert "type" in df.columns

    def test_export_parquet(self, tmp_path):
        tc = TrajectoryCollector("test_agent")
        tc.start_day(date(2024, 3, 4), {"cash": 1000000})
        tc.record_step(date(2024, 3, 4), "tool_call", {"name": "buy"})
        tc.end_day(actions=[{"action": "buy"}], reward=0.01)
        paths = tc.export_parquet(tmp_path)
        assert paths["day"].exists()
        assert paths["step"].exists()

    def test_live_trajectory_is_append_only_jsonl(self, tmp_path):
        live = tmp_path / "run_live.jsonl"
        tc = TrajectoryCollector("test_agent", live_file=live)
        tc.start_day(date(2024, 3, 4), {})
        tc.record_step(date(2024, 3, 4), "tool_call", {"name": "first"})
        first_size = live.stat().st_size
        tc.record_step(date(2024, 3, 4), "tool_call", {"name": "second"})

        lines = [json.loads(line) for line in live.read_text(encoding="utf-8").splitlines()]
        assert [line["data"]["name"] for line in lines] == ["first", "second"]
        assert live.stat().st_size > first_size
