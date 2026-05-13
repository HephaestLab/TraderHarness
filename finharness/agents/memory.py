"""DailyMemory — cross-day JSONL memory for agents."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class DailyMemory:
    """Stores and retrieves daily summaries across trading days."""

    def __init__(self, agent_id: str, storage_dir: str | Path | None = None) -> None:
        self.agent_id = agent_id
        self._entries: list[dict] = []
        self._storage_path: Path | None = None
        if storage_dir:
            self._storage_path = Path(storage_dir) / f"{agent_id}_memory.jsonl"
            self._load()

    def add(self, trade_date: date, summary: str, trades: list[dict] | None = None) -> None:
        entry = {
            "date": trade_date.isoformat(),
            "summary": summary,
            "trades": trades or [],
        }
        self._entries.append(entry)
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent(self, n: int = 5, before_date: date | None = None) -> list[dict]:
        entries = self._entries
        if before_date:
            entries = [e for e in entries if e["date"] < before_date.isoformat()]
        return entries[-n:]

    def to_prompt_text(self, before_date: date | None = None, max_entries: int = 5) -> str:
        recent = self.get_recent(max_entries, before_date)
        if not recent:
            return ""
        lines = ["=== 你的近期交易记忆 ==="]
        for entry in recent:
            lines.append(f"\n[{entry['date']}] {entry['summary']}")
            if entry.get("trades"):
                for t in entry["trades"][:3]:
                    action = t.get("action", "")
                    code = t.get("stock_code", "")
                    lines.append(f"  - {action} {code}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._entries = []
        if self._storage_path and self._storage_path.exists():
            self._storage_path.unlink()

    def _load(self) -> None:
        if self._storage_path and self._storage_path.exists():
            with open(self._storage_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(json.loads(line))

    def __len__(self) -> int:
        return len(self._entries)
