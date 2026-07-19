"""Replay mode — record LLM I/O and replay deterministically."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path


class ReplayError(RuntimeError):
    """Base error for deterministic replay failures."""


class ReplayExhaustedError(ReplayError):
    """Raised when code requests more LLM calls than a cassette contains."""


class ReplayMismatchError(ReplayError):
    """Raised when the current prompt diverges from the recorded cassette."""


def request_fingerprint(messages: list[dict], tools: list[dict] | None) -> str:
    """Return a stable digest for one complete LLM request."""
    payload = json.dumps(
        {"messages": messages, "tools": tools or []},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReplayRecorder:
    """Records all LLM inputs/outputs for deterministic replay."""

    def __init__(self, prompt_contract_version: str | None = None) -> None:
        self._entries: list[dict] = []
        self.prompt_contract_version = prompt_contract_version

    def record(self, trade_date: date, step: int, entry_type: str, data: dict) -> None:
        self._entries.append(
            {
                "date": trade_date.isoformat(),
                "step": step,
                "type": entry_type,
                **data,
            }
        )

    def record_llm_call(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None,
        output: dict,
    ) -> None:
        """Record a validated, sequential LLM response."""
        self._entries.append(
            {
                "schema_version": 1,
                "step": len(self._entries),
                "type": "llm_call",
                "request_sha256": request_fingerprint(messages, tools),
                "output": output,
            }
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        temporary = p.with_suffix(p.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8", newline="\n") as f:
            if self.prompt_contract_version is not None:
                meta = {
                    "type": "meta",
                    "schema_version": 1,
                    "prompt_contract_version": self.prompt_contract_version,
                }
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for entry in self._entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        temporary.replace(p)

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
        self.prompt_contract_version: str | None = None
        self._load(path)

    def next_response(
        self,
        messages: list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> dict | None:
        if self._index >= len(self._entries):
            return None
        entry = self._entries[self._index]
        expected = entry.get("request_sha256")
        if expected and messages is not None:
            actual = request_fingerprint(messages, tools)
            if actual != expected:
                raise ReplayMismatchError(
                    f"Replay request does not match cassette at LLM call {self._index}"
                )
        self._index += 1
        return entry

    def require_response(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> dict:
        entry = self.next_response(messages=messages, tools=tools)
        if entry is None:
            raise ReplayExhaustedError(f"Replay cassette exhausted after {self._index} LLM calls")
        if "output" not in entry:
            raise ReplayMismatchError(f"Replay entry {self._index - 1} has no LLM output")
        return entry["output"]

    def get_for_date(self, trade_date: date) -> list[dict]:
        date_str = trade_date.isoformat()
        return [e for e in self._entries if e.get("date") == date_str]

    def reset(self) -> None:
        self._index = 0

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    @property
    def remaining_entries(self) -> int:
        return len(self._entries) - self._index

    def assert_consumed(self) -> None:
        if self.remaining_entries:
            raise ReplayMismatchError(
                f"Replay finished with {self.remaining_entries} unused LLM responses"
            )

    def _load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if entry.get("type") == "meta":
                        version = entry.get("prompt_contract_version")
                        if isinstance(version, str):
                            self.prompt_contract_version = version
                    elif entry.get("type") == "llm_call":
                        self._entries.append(entry)
