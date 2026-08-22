"""Persistent paper-session lifecycle and replayable event journals."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traderharness.agents.agent_card import load_card
from traderharness.core.live_feed import FeedEvent
from traderharness.core.paper_runner import PaperRunConfig, PaperTradingRunner
from traderharness.paths import agents_dir, dataset_dir, paper_dir


@dataclass
class _ManagedPaper:
    id: str
    runner: Any
    created_at: str
    agent_id: str
    agent_name: str
    session_date: str
    mode: str
    initial_cash: float
    status: str = "running"
    clock_state: str = "starting"
    phase: str = "pre_market"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    account: dict[str, Any] = field(default_factory=dict)
    positions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[list[Any]] = field(default_factory=list)
    quote_health: dict[str, Any] = field(default_factory=dict)
    last_event: dict[str, Any] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "session_date": self.session_date,
            "mode": self.mode,
            "initial_cash": self.initial_cash,
            "clock_state": self.clock_state,
            "phase": self.phase,
            "error": self.error,
            "event_count": len(self.events),
            "account": self.account,
            "positions": self.positions,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "quote_health": self.quote_health,
            "last_event": self.last_event,
        }


PaperRunnerFactory = Callable[[Any, str, dict[str, Any]], Any]


class PaperSessionManager:
    """Own daily paper sessions and make their state crash-auditable."""

    def __init__(
        self,
        *,
        runner_factory: PaperRunnerFactory | None = None,
        storage_root: Path | None = None,
        dataset_root: Path | None = None,
        agent_root: Path | None = None,
    ) -> None:
        self._runner_factory = runner_factory or self._build_runner
        self._storage_root = Path(storage_root or paper_dir())
        self._dataset_root = Path(dataset_root or dataset_dir())
        self._agent_root = Path(agent_root or agents_dir())
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, _ManagedPaper] = {}
        self._lock = threading.RLock()
        self._load_existing()

    def start(self, request: Any) -> dict[str, Any]:
        card = load_card(request.agent_id, storage_dir=self._agent_root) or load_card(
            request.agent_id
        )
        if card is None:
            raise ValueError(f"未找到智能体卡片：{request.agent_id}")
        session_id = uuid.uuid4().hex
        card_payload = card.to_dict()
        runner = self._runner_factory(request, session_id, card_payload)
        managed = _ManagedPaper(
            id=session_id,
            runner=runner,
            created_at=datetime.now(timezone.utc).isoformat(),
            agent_id=card.id,
            agent_name=card.name,
            session_date=request.session_date,
            mode=request.mode,
            initial_cash=float(request.initial_cash),
            account={
                "cash": float(request.initial_cash),
                "equity": float(request.initial_cash),
                "return_pct": 0.0,
            },
        )
        with self._lock:
            self._sessions[session_id] = managed
            self._persist_state(managed)
        threading.Thread(
            target=self._pump,
            args=(managed,),
            name=f"traderharness-paper-feed-{session_id[:8]}",
            daemon=True,
        ).start()
        runner.start()
        return managed.public()

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            managed = self._sessions.get(session_id)
            return managed.public() if managed is not None else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = sorted(
                self._sessions.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [item.public() for item in sessions]

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            managed = self._sessions.get(session_id)
            if managed is None or managed.status in {"done", "failed", "cancelled"}:
                return False
            managed.status = "cancelling"
            self._persist_state(managed)
        if managed.runner is not None:
            managed.runner.stop()
        return True

    def artifact_path(self, session_id: str, name: str) -> Path | None:
        if name not in {"events.jsonl", "trajectory.jsonl", "state.json"}:
            return None
        with self._lock:
            if session_id not in self._sessions:
                return None
        candidate = self._session_root(session_id) / name
        return candidate if candidate.is_file() else None

    async def events(self, session_id: str):
        index = 0
        while True:
            with self._lock:
                managed = self._sessions.get(session_id)
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

    def _pump(self, managed: _ManagedPaper) -> None:
        runner = managed.runner
        while runner.running or not runner.feed.done:
            event = runner.feed.get(timeout=0.1)
            if event is not None:
                self._append_event(managed, event)
        for event in runner.feed.drain(max_events=100_000):
            self._append_event(managed, event)
        with self._lock:
            if runner.error is not None:
                managed.status = "failed"
                managed.error = str(runner.error)
            elif managed.status in {"cancelling", "cancelled"}:
                managed.status = "cancelled"
            else:
                managed.status = "done"
            managed.clock_state = managed.status
            self._persist_state(managed)

    def _append_event(self, managed: _ManagedPaper, event: FeedEvent) -> None:
        with self._lock:
            document = {
                "sequence": len(managed.events) + 1,
                "type": event.type,
                "ts": event.ts,
                "data": event.data,
            }
            managed.events.append(document)
            managed.last_event = document
            data = event.data
            if event.type == "phase_change":
                managed.phase = str(data.get("phase", managed.phase))
                managed.clock_state = "agent_working"
            elif event.type == "paper_clock":
                managed.phase = str(data.get("phase", managed.phase))
                managed.clock_state = str(data.get("state", managed.clock_state))
            elif event.type == "paper_quote":
                managed.quote_health = {
                    "source": data.get("source"),
                    "missing_codes": data.get("missing_codes", []),
                    "request_metrics": data.get("request_metrics", {}),
                    "as_of": data.get("as_of"),
                    "attention_codes": data.get("attention_codes", []),
                    "one_minute_bars": data.get("one_minute_bars", 0),
                }
            elif event.type == "paper_snapshot":
                managed.account = dict(data.get("account") or {})
                managed.positions = list(data.get("positions") or [])
                managed.trades = list(data.get("trades") or [])
                managed.quote_health.update(data.get("quote_health") or {})
                observed_at = str(data.get("observed_at") or event.ts)
                equity = managed.account.get("equity")
                if equity is not None:
                    point = [observed_at, float(equity)]
                    if not managed.equity_curve or managed.equity_curve[-1] != point:
                        managed.equity_curve.append(point)
            elif event.type == "error":
                managed.error = str(data.get("message") or data.get("error") or "模拟盘错误")
            self._append_journal(managed, document)
            self._persist_state(managed)

    def _session_root(self, session_id: str) -> Path:
        return self._storage_root / session_id

    def _persist_state(self, managed: _ManagedPaper) -> None:
        root = self._session_root(managed.id)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "state.json"
        temporary = root / "state.json.tmp"
        temporary.write_text(
            json.dumps(managed.public(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _append_journal(self, managed: _ManagedPaper, event: dict[str, Any]) -> None:
        root = self._session_root(managed.id)
        root.mkdir(parents=True, exist_ok=True)
        with (root / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _load_existing(self) -> None:
        for state_path in sorted(self._storage_root.glob("*/state.json")):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                events_path = state_path.with_name("events.jsonl")
                events = []
                if events_path.is_file():
                    for line in events_path.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            events.append(json.loads(line))
                status = str(state.get("status", "failed"))
                error = state.get("error")
                if status in {"running", "cancelling"}:
                    status = "failed"
                    error = "服务重启中断了模拟盘；审计日志已保留，请新建交易日继续运行"
                managed = _ManagedPaper(
                    id=str(state["id"]),
                    runner=None,
                    created_at=str(state["created_at"]),
                    agent_id=str(state["agent_id"]),
                    agent_name=str(state.get("agent_name", state["agent_id"])),
                    session_date=str(state["session_date"]),
                    mode=str(state.get("mode", "live")),
                    initial_cash=float(state.get("initial_cash", 1_000_000)),
                    status=status,
                    clock_state=str(state.get("clock_state", status)),
                    phase=str(state.get("phase", "pre_market")),
                    events=events,
                    error=error,
                    account=dict(state.get("account") or {}),
                    positions=list(state.get("positions") or []),
                    trades=list(state.get("trades") or []),
                    equity_curve=list(state.get("equity_curve") or []),
                    quote_health=dict(state.get("quote_health") or {}),
                    last_event=state.get("last_event"),
                )
                self._sessions[managed.id] = managed
                if status == "failed" and state.get("status") in {"running", "cancelling"}:
                    self._persist_state(managed)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def _build_runner(self, request: Any, session_id: str, agent: dict[str, Any]):
        return PaperTradingRunner(
            PaperRunConfig(
                session_id=session_id,
                agent=agent,
                session_date=datetime.fromisoformat(request.session_date).date(),
                initial_cash=float(request.initial_cash),
                mode=request.mode,
                poll_seconds=int(request.poll_seconds),
                max_attention_codes=int(request.max_attention_codes),
                dataset_root=self._dataset_root,
                artifact_root=self._session_root(session_id),
            )
        )
