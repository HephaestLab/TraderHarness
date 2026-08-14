"""Agent Card — simple agent configuration with persona text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from traderharness.paths import agents_dir
from traderharness.tools.catalog import normalize_allowed_tools

DEFAULT_STORAGE_DIR = agents_dir()
BUILTIN_STORAGE_DIR = Path(__file__).with_name("builtin")


@dataclass
class AgentCard:
    id: str
    name: str
    description: str = ""
    persona: str = "你是一位经验丰富的主观交易员。"
    strategy_tags: list[str] = field(default_factory=list)
    risk_profile: str = "balanced"
    holding_period: str = "3-10 trading days"
    allowed_tools: list[str] = field(default_factory=lambda: normalize_allowed_tools(None))
    model: str = "deepseek-v4-pro"
    initial_cash: int = 1_000_000
    max_positions: int = 4
    max_position_pct: float = 25.0
    max_pre_iterations: int = 10
    max_window_iterations: int = 3
    require_structured_plan: bool = False
    require_decision_card: bool = False
    require_phase_completion: bool = False
    minimum_holding_days: int = 0
    research_interval_days: int = 0
    sandbox_pre_market_only: bool = False
    sandbox_max_calls_per_day: int = 0
    watchlist_ttl_days: int = 0
    max_active_memories: int = 0
    max_daily_memories: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "persona": self.persona,
            "strategy_tags": list(self.strategy_tags),
            "risk_profile": self.risk_profile,
            "holding_period": self.holding_period,
            "allowed_tools": normalize_allowed_tools(self.allowed_tools),
            "model": self.model,
            "initial_cash": self.initial_cash,
            "max_positions": self.max_positions,
            "max_position_pct": self.max_position_pct,
            "max_pre_iterations": self.max_pre_iterations,
            "max_window_iterations": self.max_window_iterations,
            "require_structured_plan": self.require_structured_plan,
            "require_decision_card": self.require_decision_card,
            "require_phase_completion": self.require_phase_completion,
            "minimum_holding_days": self.minimum_holding_days,
            "research_interval_days": self.research_interval_days,
            "sandbox_pre_market_only": self.sandbox_pre_market_only,
            "sandbox_max_calls_per_day": self.sandbox_max_calls_per_day,
            "watchlist_ttl_days": self.watchlist_ttl_days,
            "max_active_memories": self.max_active_memories,
            "max_daily_memories": self.max_daily_memories,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentCard:
        persona = str(data.get("persona", "你是一位经验丰富的主观交易员。"))
        for original, replacement in (data.get("persona_replacements") or {}).items():
            persona = persona.replace(str(original), str(replacement))
        return cls(
            id=data["id"],
            name=data["name"],
            description=str(data.get("description", "")),
            persona=persona,
            strategy_tags=[str(tag) for tag in data.get("strategy_tags", [])],
            risk_profile=str(data.get("risk_profile", "balanced")),
            holding_period=str(data.get("holding_period", "3-10 trading days")),
            allowed_tools=normalize_allowed_tools(data.get("allowed_tools")),
            model=data.get("model", "deepseek-v4-pro"),
            initial_cash=data.get("initial_cash", 1_000_000),
            max_positions=data.get("max_positions", 4),
            max_position_pct=data.get("max_position_pct", 25.0),
            max_pre_iterations=int(data.get("max_pre_iterations", 10)),
            max_window_iterations=int(data.get("max_window_iterations", 3)),
            require_structured_plan=bool(data.get("require_structured_plan", False)),
            require_decision_card=bool(data.get("require_decision_card", False)),
            require_phase_completion=bool(data.get("require_phase_completion", False)),
            minimum_holding_days=max(0, int(data.get("minimum_holding_days", 0))),
            research_interval_days=max(0, int(data.get("research_interval_days", 0))),
            sandbox_pre_market_only=bool(data.get("sandbox_pre_market_only", False)),
            sandbox_max_calls_per_day=max(0, int(data.get("sandbox_max_calls_per_day", 0))),
            watchlist_ttl_days=max(0, int(data.get("watchlist_ttl_days", 0))),
            max_active_memories=max(0, int(data.get("max_active_memories", 0))),
            max_daily_memories=max(0, int(data.get("max_daily_memories", 0))),
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
    if not path.exists() and storage_dir is None:
        path = BUILTIN_STORAGE_DIR / f"{card_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentCard.from_dict(data)


def list_cards(storage_dir: Path | None = None) -> list[AgentCard]:
    directory = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
    files = list(directory.glob("*.json")) if directory.exists() else []
    if storage_dir is None and BUILTIN_STORAGE_DIR.exists():
        user_ids = {path.stem for path in files}
        files.extend(
            path for path in BUILTIN_STORAGE_DIR.glob("*.json") if path.stem not in user_ids
        )
    cards = []
    for f in sorted(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cards.append(AgentCard.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue
    return cards
