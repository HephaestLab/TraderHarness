"""Thread-safe run lifecycle and replayable WebSocket event journal."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from traderharness.agents.agent_card import load_card
from traderharness.core.live_feed import FeedEvent
from traderharness.core.runner import BacktestRunner, RunConfig
from traderharness.server.app import RunRequest


@dataclass
class _ManagedRun:
    id: str
    runner: Any
    created_at: str
    seq: int = 0
    agents: list[str] = field(default_factory=list)
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    result_file: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "error": self.error,
            "result_file": self.result_file,
            "event_count": len(self.events),
            "agents": self.agents,
        }


RunnerFactory = Callable[[RunRequest, str], Any]


class RunManager:
    """Own background runs and preserve events for reconnecting clients."""

    def __init__(self, runner_factory: RunnerFactory | None = None) -> None:
        self._runner_factory = runner_factory or self._build_runner
        self._runs: dict[str, _ManagedRun] = {}
        self._lock = threading.RLock()
        # Monotonic tiebreak for list(): datetime.now() can return identical
        # timestamps for back-to-back starts on coarse-tick platforms.
        self._seq = 0

    def start(self, request: RunRequest) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        runner = self._runner_factory(request, run_id)
        managed = _ManagedRun(
            id=run_id,
            runner=runner,
            created_at=datetime.now(timezone.utc).isoformat(),
            agents=list(request.agents),
        )
        with self._lock:
            self._seq += 1
            managed.seq = self._seq
            self._runs[run_id] = managed
        threading.Thread(
            target=self._pump,
            args=(managed,),
            name=f"traderharness-feed-{run_id[:8]}",
            daemon=True,
        ).start()
        runner.start()
        return managed.public()

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            managed = self._runs.get(run_id)
            return managed.public() if managed is not None else None

    def list(self) -> list[dict[str, Any]]:
        """Newest-first public state for every run owned by this manager."""
        with self._lock:
            runs = sorted(
                self._runs.values(),
                key=lambda managed: (managed.created_at, managed.seq),
                reverse=True,
            )
        return [managed.public() for managed in runs]

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            managed = self._runs.get(run_id)
            if managed is None or managed.status in {"done", "failed", "cancelled"}:
                return False
            managed.status = "cancelling"
        managed.runner.stop()
        return True

    async def events(self, run_id: str):
        index = 0
        while True:
            with self._lock:
                managed = self._runs.get(run_id)
                if managed is None:
                    return
                pending = managed.events[index:]
                terminal = managed.status in {"done", "failed", "cancelled"}
            for event in pending:
                index += 1
                yield event
            if terminal and not pending:
                return
            await asyncio.sleep(0.05)

    def _pump(self, managed: _ManagedRun) -> None:
        runner = managed.runner
        while runner.running or not runner.feed.done:
            event = runner.feed.get(timeout=0.1)
            if event is None:
                continue
            self._append_event(managed, event)
        for event in runner.feed.drain(max_events=10_000):
            self._append_event(managed, event)
        with self._lock:
            if runner.error is not None:
                managed.status = "failed"
                managed.error = str(runner.error)
            elif managed.status == "cancelling":
                managed.status = "cancelled"
            elif managed.status == "running":
                managed.status = "done"
            result_path = getattr(runner, "result_path", None)
            if result_path is not None:
                managed.result_file = Path(result_path).name

    def _append_event(self, managed: _ManagedRun, event: FeedEvent) -> None:
        with self._lock:
            managed.events.append(
                {
                    "sequence": len(managed.events) + 1,
                    "type": event.type,
                    "ts": event.ts,
                    "data": event.data,
                }
            )

    @staticmethod
    def _build_runner(request: RunRequest, run_id: str) -> BacktestRunner:
        agents = []
        for agent_id in request.agents:
            card = load_card(agent_id)
            if card is None:
                raise ValueError(f"未找到智能体卡片：{agent_id}")
            agents.append(card.to_dict())
        replay_path = None
        if request.replay:
            from importlib.resources import files

            resource = files("traderharness.demo").joinpath("momentum_dragon_2024-03-14.jsonl")
            candidate = Path(str(resource))
            source_candidate = (
                Path(__file__).resolve().parents[2]
                / "examples"
                / "replays"
                / "momentum_dragon_2024-03-14.jsonl"
            )
            replay_path = candidate if candidate.is_file() else source_candidate
            if not replay_path.is_file():
                raise FileNotFoundError("Bundled replay cassette is missing")
        config = RunConfig(
            start_date=date.fromisoformat(request.start_date),
            end_date=date.fromisoformat(request.end_date),
            initial_cash=request.initial_cash,
            agents=agents,
            mask_entities=request.mask_entities,
            entity_mask_seed=request.entity_mask_seed,
            replay_path=replay_path,
        )
        return BacktestRunner(config)
