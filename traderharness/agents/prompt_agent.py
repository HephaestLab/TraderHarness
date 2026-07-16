"""PromptAgent — YAML persona → LLM Agent (BYOP: Bring Your Own Persona)。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml

from finharness.agents.llm_client import LLMClient
from finharness.agents.tool_agent import ToolAgent


class PromptAgent(ToolAgent):
    """Agent loaded from a YAML persona file."""

    def __init__(self, config_path: str | Path, llm_client: LLMClient | None = None):
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Agent config not found: {config_path}")

        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        agent_id = cfg.get("id", path.stem)
        name = cfg.get("name", path.stem)
        persona = cfg.get("persona", "你是一位经验丰富的交易员。")
        model = cfg.get("model", "deepseek-chat")
        initial_cash = Decimal(str(cfg.get("initial_cash", 1_000_000)))
        max_positions = cfg.get("max_positions", 4)
        max_position_pct = cfg.get("max_position_pct", 25.0)

        if llm_client is None:
            llm_client = LLMClient(model=model)

        super().__init__(
            agent_id=agent_id,
            name=name,
            llm_client=llm_client,
            persona=persona,
            initial_cash=initial_cash,
            max_positions=max_positions,
            max_position_pct=max_position_pct,
        )
