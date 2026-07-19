"""Replay Bundle v2 — multi-agent, scope-routed replay recording and playback.

A single-file cassette (`traderharness.trajectory.replay`) works for exactly
one LLM call sequence. A Replay Bundle is a directory that can hold many
independent call sequences ("scopes") side by side, so that:

- several agents can be recorded/replayed in one run (`compare`), and
- a committee's read-only advisors can be recorded/replayed independently of
  the single trading executor.

Directory layout::

    bundle_dir/
      manifest.json
      agents/
        <agent_id>.jsonl                       # plain agent, no committee
        <committee_id>__executor.jsonl         # committee executor
        <committee_id>__advisor_<role>.jsonl   # one file per advisor role

`ScopedReplayRecorder`/`ScopedReplayPlayer` fan calls out to per-scope
`ReplayRecorder`/`ReplayPlayer` instances (see `replay.py`) so the existing
fingerprint validation, exhaustion, and mismatch behavior is reused unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from traderharness.trajectory.replay import ReplayPlayer, ReplayRecorder

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_FILENAME = "manifest.json"
AGENTS_DIRNAME = "agents"


def executor_scope_id(agent_id: str, *, is_committee: bool = False) -> str:
    """Scope id for an agent's trading executor.

    Plain (non-committee) agents keep the bare `agent_id` for backward-friendly
    file names. Committees are suffixed with `__executor` so the executor's
    cassette does not collide with advisor cassettes under the same agent id.
    """
    return f"{agent_id}__executor" if is_committee else agent_id


def advisor_scope_id(agent_id: str, role: str) -> str:
    """Scope id for a single committee advisor's read-only LLM calls."""
    return f"{agent_id}__advisor_{role}"


def cassette_filename(scope_id: str) -> str:
    return f"{scope_id}.jsonl"


def is_bundle_path(path: str | Path) -> bool:
    """Decide whether `path` refers to a Replay Bundle directory (v2) rather
    than a single-file JSONL cassette (v1).

    Existing directories are always bundles; existing files are bundles only
    if they are not `.jsonl`. When `path` does not exist yet (a
    `--record-replay` target that will be created), the `.jsonl` suffix is
    the only available signal.
    """
    p = Path(path)
    if p.is_dir():
        return True
    if p.exists():
        return p.suffix != ".jsonl"
    return p.suffix != ".jsonl"


@dataclass
class AgentManifestEntry:
    """One agent's manifest record: identity, model, and its cassette file."""

    id: str
    name: str = ""
    model: str = ""
    card_snapshot: dict[str, Any] | None = None
    cassette: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "card_snapshot": self.card_snapshot,
            "cassette": self.cassette,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentManifestEntry:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            model=data.get("model", ""),
            card_snapshot=data.get("card_snapshot"),
            cassette=data.get("cassette", ""),
        )


@dataclass
class ReplayBundleManifest:
    """Top-level `manifest.json` contract for a Replay Bundle."""

    start_date: date
    end_date: date
    initial_cash: float = 1_000_000.0
    mask_entities: bool = True
    entity_mask_seed: int = 0
    agents: list[AgentManifestEntry] = field(default_factory=list)
    prompt_contract_version: str = "v1"
    thinking: dict[str, Any] = field(default_factory=lambda: {"enabled": False, "effort": None})
    created_at: str = ""
    traderharness_version: str = ""
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def agent_by_id(self, agent_id: str) -> AgentManifestEntry | None:
        return next((agent for agent in self.agents if agent.id == agent_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_cash": self.initial_cash,
            "mask_entities": self.mask_entities,
            "entity_mask_seed": self.entity_mask_seed,
            "agents": [agent.to_dict() for agent in self.agents],
            "prompt_contract_version": self.prompt_contract_version,
            "thinking": self.thinking,
            "created_at": self.created_at,
            "traderharness_version": self.traderharness_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayBundleManifest:
        return cls(
            start_date=date.fromisoformat(data["start_date"]),
            end_date=date.fromisoformat(data["end_date"]),
            initial_cash=data.get("initial_cash", 1_000_000.0),
            mask_entities=data.get("mask_entities", True),
            entity_mask_seed=data.get("entity_mask_seed", 0),
            agents=[AgentManifestEntry.from_dict(a) for a in data.get("agents", [])],
            prompt_contract_version=data.get("prompt_contract_version", "v1"),
            thinking=data.get("thinking") or {"enabled": False, "effort": None},
            created_at=data.get("created_at", ""),
            traderharness_version=data.get("traderharness_version", ""),
            schema_version=data.get("schema_version", MANIFEST_SCHEMA_VERSION),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> ReplayBundleManifest:
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))


class _ScopedRecorderHandle:
    """Drop-in `replay_recorder` for `LLMClient`, bound to one scope id.

    `LLMClient.record_replay_call` only ever calls `.record_llm_call(...)`,
    so this handle can be passed straight into `LLMClient(replay_recorder=...)`
    without any change to `LLMClient` itself.
    """

    def __init__(self, parent: ScopedReplayRecorder, scope_id: str) -> None:
        self._parent = parent
        self._scope_id = scope_id

    def record_llm_call(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None,
        output: dict,
    ) -> None:
        self._parent.recorder_for(self._scope_id).record_llm_call(
            messages=messages, tools=tools, output=output
        )

    @property
    def entries(self) -> list[dict]:
        return self._parent.recorder_for(self._scope_id).entries

    def __len__(self) -> int:
        return len(self._parent.recorder_for(self._scope_id))


class ScopedReplayRecorder:
    """Fan-out recorder: one independent `ReplayRecorder` per scope id.

    Use `.scope(scope_id)` to obtain a handle to hand to `LLMClient(...)` for
    a given agent's executor or a committee advisor. Once a run finishes,
    `save_bundle` persists every scope's cassette plus `manifest.json`.
    """

    def __init__(self) -> None:
        self._recorders: dict[str, ReplayRecorder] = {}

    def recorder_for(self, scope_id: str) -> ReplayRecorder:
        return self._recorders.setdefault(scope_id, ReplayRecorder())

    def scope(self, scope_id: str) -> _ScopedRecorderHandle:
        self.recorder_for(scope_id)
        return _ScopedRecorderHandle(self, scope_id)

    @property
    def scope_ids(self) -> list[str]:
        return list(self._recorders.keys())

    def save_bundle(self, bundle_dir: str | Path, manifest: ReplayBundleManifest) -> Path:
        bundle_dir = Path(bundle_dir)
        agents_dir = bundle_dir / AGENTS_DIRNAME
        agents_dir.mkdir(parents=True, exist_ok=True)
        for scope_id, recorder in self._recorders.items():
            recorder.save(agents_dir / cassette_filename(scope_id))
        manifest_path = bundle_dir / MANIFEST_FILENAME
        manifest.save(manifest_path)
        return manifest_path


class ScopedReplayPlayer:
    """Loads a Replay Bundle directory and hands out per-scope `ReplayPlayer`s.

    Each `.scope(scope_id)` result is a real `ReplayPlayer`, so it can be
    passed directly as `LLMClient(replay_player=...)` with no wrapper needed.
    """

    def __init__(self, bundle_dir: str | Path) -> None:
        self.bundle_dir = Path(bundle_dir)
        manifest_path = self.bundle_dir / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Replay bundle manifest not found: {manifest_path}")
        self.manifest = ReplayBundleManifest.load(manifest_path)
        self._players: dict[str, ReplayPlayer] = {}

    def has_scope(self, scope_id: str) -> bool:
        return (self.bundle_dir / AGENTS_DIRNAME / cassette_filename(scope_id)).is_file()

    def scope(self, scope_id: str) -> ReplayPlayer:
        if scope_id not in self._players:
            path = self.bundle_dir / AGENTS_DIRNAME / cassette_filename(scope_id)
            if not path.is_file():
                raise FileNotFoundError(
                    f"No recorded cassette for scope '{scope_id}' in bundle {self.bundle_dir}"
                )
            self._players[scope_id] = ReplayPlayer(path)
        return self._players[scope_id]

    def assert_all_consumed(self) -> None:
        for player in self._players.values():
            player.assert_consumed()
