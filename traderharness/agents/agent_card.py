"""Agent Card — simple agent configuration with persona text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

DEFAULT_STORAGE_DIR = Path.home() / ".finharness" / "agents"


@dataclass
class AgentCard:
    id: str
    name: str
    persona: str = "你是一位经验丰富的主观交易员。"
    model: str = "deepseek-v4-pro"
    initial_cash: int = 1_000_000
    max_positions: int = 4
    max_position_pct: float = 25.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "model": self.model,
            "initial_cash": self.initial_cash,
            "max_positions": self.max_positions,
            "max_position_pct": self.max_position_pct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            id=data["id"],
            name=data["name"],
            persona=data.get("persona", "你是一位经验丰富的主观交易员。"),
            model=data.get("model", "deepseek-v4-pro"),
            initial_cash=data.get("initial_cash", 1_000_000),
            max_positions=data.get("max_positions", 4),
            max_position_pct=data.get("max_position_pct", 25.0),
        )


def save_card(card: AgentCard, storage_dir: Path | None = None) -> Path:
    directory = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{card.id}.json"
    path.write_text(
        json.dumps(card.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_card(card_id: str, storage_dir: Path | None = None) -> AgentCard | None:
    directory = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
    path = directory / f"{card_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentCard.from_dict(data)


def list_cards(storage_dir: Path | None = None) -> list[AgentCard]:
    directory = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
    if not directory.exists():
        return []
    cards = []
    for f in sorted(directory.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cards.append(AgentCard.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue
    return cards
