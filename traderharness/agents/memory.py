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

    def to_prompt_text(
        self,
        before_date: date | None = None,
        max_tokens: int = 8000,
        entity_masker=None,
    ) -> str:
        """Append-mode memory with date masking — uses relative day index instead of calendar dates."""
        entries = self._entries
        if before_date:
            entries = [e for e in entries if e["date"] < before_date.isoformat()]
        if not entries:
            return ""

        total = len(entries)

        # Build full text — use "Day N" instead of ISO dates
        full_lines = ["=== 你的交易记忆 ==="]
        for i, entry in enumerate(entries):
            day_label = f"第{i + 1}天" if i < total - 1 else "昨天"
            full_lines.append(f"\n[{day_label}] {entry['summary']}")
            if entry.get("trades"):
                for t in entry["trades"][:3]:
                    action = t.get("action", "")
                    code = t.get("stock_code", "")
                    full_lines.append(f"  - {action} {code}")
        full_text = "\n".join(full_lines)

        # Estimate tokens (rough: 1 token ≈ 2 chars for Chinese)
        est_tokens = len(full_text) // 2
        if est_tokens <= max_tokens:
            return entity_masker.mask_text(full_text) if entity_masker is not None else full_text

        # Over budget: compress earlier entries, keep recent 5 days full
        recent_count = min(5, len(entries))
        early = entries[:-recent_count] if recent_count < len(entries) else []
        recent = entries[-recent_count:]

        lines = ["=== 你的交易记忆 ==="]

        if early:
            lines.append(f"\n[早期摘要: 第1天 ~ 第{len(early)}天]")
            for j, entry in enumerate(early):
                summary = entry["summary"][:60]
                trade_count = len(entry.get("trades", []))
                lines.append(
                    f"  第{j + 1}天: {summary}{'...' if len(entry['summary']) > 60 else ''} ({trade_count}笔交易)"
                )

        start_idx = len(early)
        for j, entry in enumerate(recent):
            day_idx = start_idx + j + 1
            day_label = f"第{day_idx}天" if j < len(recent) - 1 else "昨天"
            lines.append(f"\n[{day_label}] {entry['summary']}")
            if entry.get("trades"):
                for t in entry["trades"][:3]:
                    action = t.get("action", "")
                    code = t.get("stock_code", "")
                    lines.append(f"  - {action} {code}")

        text = "\n".join(lines)
        return entity_masker.mask_text(text) if entity_masker is not None else text

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
