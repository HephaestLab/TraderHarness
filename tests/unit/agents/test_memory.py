"""Tests for DailyMemory."""

from datetime import date

from traderharness.agents.memory import DailyMemory
from traderharness.core.entity_masking import EntityMasker


class TestDailyMemory:
    def test_add_and_retrieve(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Bought 600519", [{"action": "buy", "stock_code": "600519"}])
        assert len(mem) == 1

    def test_get_recent(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Day 1")
        mem.add(date(2024, 3, 5), "Day 2")
        mem.add(date(2024, 3, 6), "Day 3")
        recent = mem.get_recent(2)
        assert len(recent) == 2
        assert recent[0]["summary"] == "Day 2"

    def test_get_recent_before_date(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Day 1")
        mem.add(date(2024, 3, 5), "Day 2")
        recent = mem.get_recent(5, before_date=date(2024, 3, 5))
        assert len(recent) == 1
        assert recent[0]["summary"] == "Day 1"

    def test_to_prompt_text(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Bought Moutai")
        text = mem.to_prompt_text()
        assert "Bought Moutai" in text
        # dates are masked to relative labels — real calendar dates must not leak
        assert "2024-03-04" not in text
        assert "昨天" in text

    def test_persistence(self, tmp_path):
        mem = DailyMemory(agent_id="test", storage_dir=tmp_path)
        mem.add(date(2024, 3, 4), "Persisted entry")
        mem2 = DailyMemory(agent_id="test", storage_dir=tmp_path)
        assert len(mem2) == 1
        assert mem2.get_recent(1)[0]["summary"] == "Persisted entry"

    def test_prompt_text_masks_summary_and_trade_codes(self):
        mem = DailyMemory(agent_id="test")
        mem.add(
            date(2024, 3, 4),
            "贵州茅台600519仍然值得持有",
            [{"action": "buy", "stock_code": "600519"}],
        )
        masker = EntityMasker(
            ["600519", "600000"],
            names={"600519": "贵州茅台", "600000": "浦发银行"},
            seed=1,
        )

        text = mem.to_prompt_text(entity_masker=masker)

        assert masker.mask_code("600519") in text
        assert "贵州茅台" not in text
        assert "600519" not in text

    def test_clear(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Entry")
        mem.clear()
        assert len(mem) == 0
