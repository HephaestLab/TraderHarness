"""Replay mode — record LLM I/O and replay deterministically."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


class ReplayRecorder:
    """Records all LLM inputs/outputs for deterministic replay."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def record(self, trade_date: date, step: int, entry_type: str, data: dict) -> None:
        self._entries.append({
            "date": trade_date.isoformat(),
            "step": step,
            "type": entry_type,
            **data,
        })

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


class ReplayPlayer:
    """Replays recorded LLM responses without calling the API."""

    def __init__(self, path: str | Path) -> None:
        self._entries: list[dict] = []
        self._index: int = 0
        self._load(path)

    def next_response(self) -> dict | None:
        if self._index >= len(self._entries):
            return None
        entry = self._entries[self._index]
        self._index += 1
        return entry

    def get_for_date(self, trade_date: date) -> list[dict]:
        date_str = trade_date.isoformat()
        return [e for e in self._entries if e.get("date") == date_str]

    def reset(self) -> None:
        self._index = 0

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    def _load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._entries.append(json.loads(line))
