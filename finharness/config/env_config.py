"""Environment configuration loading from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml


@dataclass
class BacktestConfig:
    start: date = date(2024, 1, 2)
    end: date = date(2024, 12, 31)
    initial_cash: Decimal = Decimal("1000000")
    warmup_days: int = 0
    dataset: str = ""


@dataclass
class EnvYAMLConfig:
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    data_dir: str = ""
    cache_enabled: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "EnvYAMLConfig":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(p) as f:
            raw = yaml.safe_load(f) or {}
        bt_raw = raw.get("backtest", {})
        backtest = BacktestConfig(
            start=_parse_date(bt_raw.get("start", "2024-01-02")),
            end=_parse_date(bt_raw.get("end", "2024-12-31")),
            initial_cash=Decimal(str(bt_raw.get("initial_cash", 1_000_000))),
            warmup_days=int(bt_raw.get("warmup_days", 0)),
            dataset=bt_raw.get("dataset", ""),
        )
        return cls(
            backtest=backtest,
            data_dir=raw.get("data_dir", ""),
            cache_enabled=raw.get("cache_enabled", True),
            log_level=raw.get("log_level", "INFO"),
        )


@dataclass
class AgentYAMLConfig:
    name: str = ""
    model: str = ""
    persona: str = ""
    tools: list[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens_per_day: int = 0

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentYAMLConfig":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Agent config not found: {path}")
        with open(p) as f:
            raw = yaml.safe_load(f) or {}
        return cls(
            name=raw.get("name", p.stem),
            model=raw.get("model", ""),
            persona=raw.get("persona", ""),
            tools=raw.get("tools", []),
            temperature=float(raw.get("temperature", 0.7)),
            max_tokens_per_day=int(raw.get("max_tokens_per_day", 0)),
        )


def _parse_date(s: str) -> date:
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s))
