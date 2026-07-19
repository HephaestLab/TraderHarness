"""Tests for simplified Agent Card system."""


import pytest

from traderharness.agents.agent_card import (
    BUILTIN_STORAGE_DIR,
    AgentCard,
    list_cards,
    load_card,
    save_card,
)
from traderharness.tools.catalog import CORE_TOOL_NAMES


class TestAgentCard:
    def test_create_minimal(self):
        card = AgentCard(id="test", name="Test")
        assert card.id == "test"
        assert card.name == "Test"
        assert card.model == "deepseek-v4-pro"
        assert card.initial_cash == 1_000_000
        assert card.max_positions == 4

    def test_create_full(self):
        card = AgentCard(
            id="aggressive",
            name="Aggro Trader",
            persona="追涨杀跌，快进快出。",
            model="deepseek-v4-flash",
            initial_cash=2_000_000,
            max_positions=6,
            max_position_pct=30.0,
        )
        assert card.persona == "追涨杀跌，快进快出。"
        assert card.max_positions == 6

    def test_to_dict_roundtrip(self):
        card = AgentCard(
            id="value-king",
            name="Value King",
            persona="只买便宜的好公司。",
        )
        d = card.to_dict()
        restored = AgentCard.from_dict(d)
        assert restored.id == card.id
        assert restored.persona == card.persona
        assert restored.model == card.model

    def test_from_dict_with_missing_fields(self):
        data = {"id": "minimal", "name": "Minimal"}
        card = AgentCard.from_dict(data)
        assert card.persona == "你是一位经验丰富的主观交易员。"
        assert card.initial_cash == 1_000_000

    def test_strategy_metadata_and_tool_policy_roundtrip(self):
        card = AgentCard(
            id="quality",
            name="Quality",
            description="以质量和估值为双重门槛。",
            strategy_tags=["quality", "value"],
            risk_profile="conservative",
            holding_period="20-60 trading days",
            allowed_tools=[
                *sorted(CORE_TOOL_NAMES),
                "get_fundamentals",
                "get_valuation",
            ],
        )

        restored = AgentCard.from_dict(card.to_dict())

        assert restored.description == card.description
        assert restored.strategy_tags == ["quality", "value"]
        assert restored.risk_profile == "conservative"
        assert restored.holding_period == "20-60 trading days"
        assert set(restored.allowed_tools) == set(card.allowed_tools)


class TestSaveLoadCards:
    def test_save_and_load(self, tmp_path):
        card = AgentCard(id="test-save", name="Test Save", persona="Hello world.")
        save_card(card, storage_dir=tmp_path)

        loaded = load_card("test-save", storage_dir=tmp_path)
        assert loaded is not None
        assert loaded.name == "Test Save"
        assert loaded.persona == "Hello world."

    def test_load_nonexistent_returns_none(self, tmp_path):
        loaded = load_card("does-not-exist", storage_dir=tmp_path)
        assert loaded is None

    def test_list_cards(self, tmp_path):
        for i in range(3):
            card = AgentCard(id=f"agent-{i}", name=f"Agent {i}")
            save_card(card, storage_dir=tmp_path)

        cards = list_cards(storage_dir=tmp_path)
        assert len(cards) == 3
        ids = {c.id for c in cards}
        assert ids == {"agent-0", "agent-1", "agent-2"}

    def test_overwrite_existing(self, tmp_path):
        card = AgentCard(id="mutable", name="V1", persona="old")
        save_card(card, storage_dir=tmp_path)

        card_v2 = AgentCard(id="mutable", name="V2", persona="new")
        save_card(card_v2, storage_dir=tmp_path)

        loaded = load_card("mutable", storage_dir=tmp_path)
        assert loaded.name == "V2"
        assert loaded.persona == "new"


class TestFromCard:
    def test_tool_agent_from_card(self, tmp_path, monkeypatch):
        import traderharness.agents.agent_card as card_mod

        monkeypatch.setattr(card_mod, "DEFAULT_STORAGE_DIR", tmp_path)

        card = AgentCard(
            id="test-from-card",
            name="Test From Card",
            persona="我是测试 agent。",
            model="deepseek-chat",
            initial_cash=500_000,
            max_positions=3,
            max_position_pct=30.0,
        )
        save_card(card, storage_dir=tmp_path)

        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent

        llm = LLMClient(model="deepseek-chat", api_key="fake", base_url="http://fake")
        agent = ToolAgent.from_card("test-from-card", llm_client=llm)

        assert agent.agent_id == "test-from-card"
        assert agent.name == "Test From Card"
        assert agent.max_positions == 3
        assert "测试" in agent.persona

    def test_from_card_applies_tool_allowlist_and_protected_core(self, tmp_path, monkeypatch):
        import traderharness.agents.agent_card as card_mod

        monkeypatch.setattr(card_mod, "DEFAULT_STORAGE_DIR", tmp_path)
        save_card(
            AgentCard(
                id="focused",
                name="Focused",
                model="deepseek-chat",
                allowed_tools=["get_kline"],
            ),
            storage_dir=tmp_path,
        )

        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent

        llm = LLMClient(model="deepseek-chat", api_key="fake", base_url="http://fake")
        agent = ToolAgent.from_card("focused", llm_client=llm)

        assert "get_kline" in agent._registry
        assert CORE_TOOL_NAMES <= set(agent._registry._tools)
        assert "execute_code" not in agent._registry

    def test_from_card_not_found(self, tmp_path, monkeypatch):
        import traderharness.agents.agent_card as card_mod
        monkeypatch.setattr(card_mod, "DEFAULT_STORAGE_DIR", tmp_path)

        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent

        llm = LLMClient(model="deepseek-chat", api_key="fake", base_url="http://fake")
        with pytest.raises(FileNotFoundError):
            ToolAgent.from_card("nonexistent", llm_client=llm)


def test_builtin_registry_uses_deepseek_v4_pro_model():
    """All bundled builtin agent cards should use the flagship model, not a mix."""
    cards = {
        path.stem: load_card(path.stem, BUILTIN_STORAGE_DIR)
        for path in BUILTIN_STORAGE_DIR.glob("*.json")
    }
    assert cards
    for card_id, card in cards.items():
        assert card is not None
        assert card.model == "deepseek-v4-pro", f"{card_id} still uses {card.model}"


def test_builtin_registry_contains_distinct_production_strategies():
    expected = {
        "quality-compounder",
        "event-hawk",
        "sector-rotator",
        "contrarian-guardian",
        "quant-researcher",
        "trend-breakout",
    }
    cards = {
        path.stem: load_card(path.stem, BUILTIN_STORAGE_DIR)
        for path in BUILTIN_STORAGE_DIR.glob("*.json")
    }

    assert expected <= set(cards)
    for card_id in expected:
        card = cards[card_id]
        assert card is not None
        assert len(card.persona) >= 300
        assert card.description
        assert len(card.strategy_tags) >= 2
        assert CORE_TOOL_NAMES <= set(card.allowed_tools)
