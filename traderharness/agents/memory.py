"""Deterministic, layered and auditable memory for trading agents.

The design deliberately separates three concerns:

* a compact set of active durable memories that is always injected;
* append-only daily journals, with only recent entries injected in full;
* deterministic on-demand retrieval over older records.

No embedding service is used in the benchmark path.  Retrieval therefore
remains reproducible and cannot leak information through a remote index.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


def _tokens(text: str) -> set[str]:
    lowered = str(text).lower()
    tokens = set(re.findall(r"[a-z0-9_]+", lowered))
    for chunk in re.findall(r"[\u3400-\u9fff]+", lowered):
        tokens.add(chunk)
        tokens.update(chunk[i : i + 2] for i in range(max(0, len(chunk) - 1)))
    return tokens


class DailyMemory:
    """Layered cross-day memory with an append-only JSONL audit log.

    ``add``/``get_recent`` retain the original DailyMemory API.  Structured
    memories use ``remember``/``search``/``get`` and can supersede an older
    record without destroying its audit history.
    """

    def __init__(self, agent_id: str, storage_dir: str | Path | None = None) -> None:
        self.agent_id = agent_id
        self._entries: list[dict] = []
        self._records: dict[str, dict] = {}
        self._events: list[dict] = []
        self._next_id = 1
        self._storage_path: Path | None = None
        if storage_dir:
            self._storage_path = Path(storage_dir) / f"{agent_id}_memory.jsonl"
            self._load()

    def add(self, trade_date: date, summary: str, trades: list[dict] | None = None) -> None:
        entry = {
            "event": "daily_journal",
            "date": trade_date.isoformat(),
            "summary": str(summary),
            "trades": trades or [],
        }
        self._apply_event(entry)
        self._append_event(entry)

    def remember(
        self,
        observed_on: date,
        content: str,
        *,
        memory_type: str = "lesson",
        tags: list[str] | None = None,
        importance: float = 0.5,
        source: str = "agent",
        supersedes_id: str | None = None,
    ) -> dict:
        """Store a durable fact/lesson and optionally supersede an older one."""
        content = str(content).strip()
        if not content:
            raise ValueError("memory content cannot be empty")
        importance = min(1.0, max(0.0, float(importance)))
        if supersedes_id:
            previous = self._records.get(str(supersedes_id))
            if previous is None:
                raise ValueError(f"unknown memory_id: {supersedes_id}")
            if previous.get("status") != "active":
                raise ValueError(f"memory is not active: {supersedes_id}")
            event = {
                "event": "supersede",
                "date": observed_on.isoformat(),
                "memory_id": str(supersedes_id),
            }
            self._apply_event(event)
            self._append_event(event)

        # Four digits avoid colliding with six-digit A-share code masking.
        memory_id = f"mem-{self._next_id:04d}"
        self._next_id += 1
        event = {
            "event": "remember",
            "date": observed_on.isoformat(),
            "memory_id": memory_id,
            "memory_type": str(memory_type or "lesson"),
            "content": content,
            "tags": sorted({str(tag).strip() for tag in tags or [] if str(tag).strip()}),
            "importance": importance,
            "source": str(source or "agent"),
            "status": "active",
            "supersedes_id": str(supersedes_id) if supersedes_id else None,
        }
        self._apply_event(event)
        self._append_event(event)
        return copy.deepcopy(self._records[memory_id])

    @staticmethod
    def _status_at(record: dict, cutoff: str | None) -> str:
        status = str(record.get("status", "active"))
        if (
            status == "superseded"
            and cutoff is not None
            and str(record.get("superseded_on", "")) >= cutoff
        ):
            return "active"
        return status

    def get(self, memory_id: str, *, before_date: date | None = None) -> dict | None:
        record = self._records.get(str(memory_id))
        cutoff = before_date.isoformat() if before_date else None
        if record is None or (cutoff and record.get("date", "") >= cutoff):
            return None
        visible = copy.deepcopy(record)
        visible["status"] = self._status_at(record, cutoff)
        return visible

    def search(
        self,
        query: str,
        *,
        before_date: date | None = None,
        memory_type: str | None = None,
        max_results: int = 5,
    ) -> list[dict]:
        """Return active memories ranked by deterministic lexical overlap."""
        query_text = str(query).strip().lower()
        query_tokens = _tokens(query_text)
        cutoff = before_date.isoformat() if before_date else None
        ranked: list[tuple[float, str, dict]] = []
        for record in self._records.values():
            if self._status_at(record, cutoff) != "active":
                continue
            if cutoff and record["date"] >= cutoff:
                continue
            if memory_type and record.get("memory_type") != memory_type:
                continue
            haystack = " ".join(
                [record.get("content", ""), record.get("memory_type", ""), *record.get("tags", [])]
            ).lower()
            candidate_tokens = _tokens(haystack)
            overlap = len(query_tokens & candidate_tokens)
            phrase = 1.0 if query_text and query_text in haystack else 0.0
            if query_tokens and not overlap and not phrase:
                continue
            score = phrase * 2.0 + overlap / max(1, len(query_tokens))
            score += float(record.get("importance", 0.5)) * 0.05
            ranked.append((score, record["memory_id"], record))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [copy.deepcopy(item[2]) for item in ranked[: max(1, min(int(max_results), 20))]]

    def audit_events(self) -> list[dict]:
        return copy.deepcopy(self._events)

    def flush_runtime_state(self, observed_on: date, state: dict[str, Any]) -> dict | None:
        """Persist hard environment state before conversation compaction.

        Only a changed snapshot creates events.  The previous snapshot is
        superseded, so prompts contain one current version while JSONL keeps
        the complete history.
        """
        content = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
        active = next(
            (
                record
                for record in self._records.values()
                if record.get("status") == "active"
                and record.get("memory_type") == "runtime_state"
            ),
            None,
        )
        if active is not None and active.get("content") == content:
            return None
        return self.remember(
            observed_on,
            content,
            memory_type="runtime_state",
            tags=["environment", "positions", "conditional_orders"],
            importance=1.0,
            source="environment",
            supersedes_id=active["memory_id"] if active is not None else None,
        )

    def get_recent(self, n: int = 5, before_date: date | None = None) -> list[dict]:
        entries = self._entries
        if before_date:
            entries = [entry for entry in entries if entry["date"] < before_date.isoformat()]
        return copy.deepcopy(entries[-n:])

    def to_prompt_text(
        self,
        before_date: date | None = None,
        max_tokens: int = 8000,
        entity_masker=None,
    ) -> str:
        """Render compact core memory plus recent episodic journals.

        Dates are represented by relative sequence labels.  Structured memory
        IDs remain visible so the agent can retrieve or supersede a record.
        """
        cutoff = before_date.isoformat() if before_date else None
        active = [
            record
            for record in self._records.values()
            if self._status_at(record, cutoff) == "active"
            and (not cutoff or record["date"] < cutoff)
        ]
        active.sort(key=lambda item: (-float(item.get("importance", 0.5)), item["memory_id"]))
        entries = self._entries
        if cutoff:
            entries = [entry for entry in entries if entry["date"] < cutoff]
        if not active and not entries:
            return ""

        lines = ["=== 结构化长期记忆（环境持久化，可按 ID 检索） ==="]
        for record in active[:20]:
            tags = f" tags={','.join(record['tags'])}" if record.get("tags") else ""
            lines.append(
                f"- [{record['memory_id']}/{record['memory_type']}{tags}] {record['content']}"
            )

        lines.append("\n=== 近期交易日志 ===")
        recent_count = min(5, len(entries))
        early = entries[:-recent_count] if recent_count < len(entries) else []
        recent = entries[-recent_count:]
        if early:
            lines.append(f"- 更早的 {len(early)} 个交易日已归档；需要时调用 search_memory。")
        start_idx = len(early)
        for offset, entry in enumerate(recent):
            day_idx = start_idx + offset + 1
            day_label = f"第{day_idx}天" if offset < len(recent) - 1 else "昨天"
            lines.append(f"\n[{day_label}] {entry['summary']}")
            for trade in entry.get("trades", [])[:3]:
                lines.append(f"  - {trade.get('action', '')} {trade.get('stock_code', '')}")

        text = "\n".join(lines)
        # Keep durable memories intact; shrink only journal prose if necessary.
        max_chars = max(400, int(max_tokens) * 2)
        if len(text) > max_chars:
            core_end = lines.index("\n=== 近期交易日志 ===") + 1
            compact = lines[:core_end]
            if entries:
                compact.append(f"- 共 {len(entries)} 个交易日日志；最近一日：{entries[-1]['summary'][:160]}")
            text = "\n".join(compact)
        return entity_masker.mask_text(text) if entity_masker is not None else text

    def clear(self) -> None:
        self._entries = []
        self._records = {}
        self._events = []
        self._next_id = 1
        if self._storage_path and self._storage_path.exists():
            self._storage_path.unlink()

    def _append_event(self, event: dict[str, Any]) -> None:
        self._events.append(copy.deepcopy(event))
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _apply_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event")
        if event_type in (None, "daily_journal"):
            # ``None`` is the legacy JSONL shape used by older runs.
            self._entries.append(
                {
                    "date": event["date"],
                    "summary": event.get("summary", ""),
                    "trades": event.get("trades", []),
                }
            )
            return
        if event_type == "remember":
            self._records[event["memory_id"]] = copy.deepcopy(event)
            match = re.search(r"(\d+)$", str(event["memory_id"]))
            if match:
                self._next_id = max(self._next_id, int(match.group(1)) + 1)
            return
        if event_type == "supersede":
            record = self._records.get(event["memory_id"])
            if record is not None:
                record["status"] = "superseded"
                record["superseded_on"] = event["date"]

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        with open(self._storage_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                self._apply_event(event)
                self._events.append(copy.deepcopy(event))

    def __len__(self) -> int:
        return len(self._entries)
