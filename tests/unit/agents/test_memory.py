"""Tests for DailyMemory."""

from datetime import date

from traderharness.agents.memory import DailyMemory
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.masking import DateMasker


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

    def test_prompt_text_masks_dates_inside_runtime_state_and_external_aliases(self):
        mem = DailyMemory(agent_id="test")
        mem.flush_runtime_state(
            date(2024, 3, 5),
            {
                "entry_date": "2024-03-04",
                "note": "贵州茅台对手是中国平安",
            },
        )
        masker = EntityMasker(
            ["600519", "600000"],
            names={"600519": "贵州茅台", "600000": "浦发银行"},
            sanitize_aliases={"601318": ["中国平安"]},
            seed=1,
        )

        text = mem.to_prompt_text(
            before_date=date(2024, 3, 6),
            date_masker=DateMasker(anchor=date(2024, 3, 6)),
            entity_masker=masker,
        )

        assert "2024-03-04" not in text
        assert "贵州茅台" not in text
        assert "中国平安" not in text
        assert "D-2" in text
        assert "外部公司" in text

    def test_clear(self):
        mem = DailyMemory(agent_id="test")
        mem.add(date(2024, 3, 4), "Entry")
        mem.clear()
        assert len(mem) == 0

    def test_durable_memory_is_always_visible_and_searchable(self):
        mem = DailyMemory(agent_id="test")
        record = mem.remember(
            date(2024, 3, 4),
            "Breakout entries without volume confirmation failed repeatedly",
            memory_type="lesson",
            tags=["breakout", "volume"],
            importance=0.9,
        )
        for day in range(5, 13):
            mem.add(date(2024, 3, day), f"Daily journal {day}")

        prompt = mem.to_prompt_text(before_date=date(2024, 3, 13), max_tokens=400)
        hits = mem.search("breakout volume", before_date=date(2024, 3, 13))

        assert record["memory_id"].startswith("mem-")
        assert "Breakout entries" in prompt
        assert hits[0]["memory_id"] == record["memory_id"]

    def test_superseded_memory_keeps_audit_history_but_not_active_prompt(self):
        mem = DailyMemory(agent_id="test")
        old = mem.remember(
            date(2024, 3, 4),
            "Original stop is 9.40",
            memory_type="position_plan",
            tags=["600519"],
        )
        new = mem.remember(
            date(2024, 3, 6),
            "Protected stop is raised to 10.20",
            memory_type="position_plan",
            tags=["600519"],
            supersedes_id=old["memory_id"],
        )

        assert mem.get(old["memory_id"])["status"] == "superseded"
        assert mem.get(new["memory_id"])["status"] == "active"
        prompt = mem.to_prompt_text(before_date=date(2024, 3, 7))
        assert "Protected stop" in prompt
        assert "Original stop" not in prompt

    def test_structured_memory_persists_append_only_events(self, tmp_path):
        mem = DailyMemory(agent_id="test", storage_dir=tmp_path)
        first = mem.remember(date(2024, 3, 4), "Risk off below breadth 35%", tags=["risk"])
        mem.remember(
            date(2024, 3, 5),
            "Risk off below breadth 30%",
            tags=["risk"],
            supersedes_id=first["memory_id"],
        )

        restored = DailyMemory(agent_id="test", storage_dir=tmp_path)

        assert len(restored.audit_events()) == 3
        assert len(restored.search("risk breadth")) == 1

    def test_future_supersession_does_not_change_an_earlier_point_in_time(self):
        mem = DailyMemory(agent_id="test")
        old = mem.remember(date(2024, 3, 4), "Original risk rule", memory_type="risk_rule")
        mem.remember(
            date(2024, 3, 8),
            "Revised risk rule",
            memory_type="risk_rule",
            supersedes_id=old["memory_id"],
        )

        prompt = mem.to_prompt_text(before_date=date(2024, 3, 6))
        record = mem.get(old["memory_id"], before_date=date(2024, 3, 6))

        assert "Original risk rule" in prompt
        assert "Revised risk rule" not in prompt
        assert record["status"] == "active"
