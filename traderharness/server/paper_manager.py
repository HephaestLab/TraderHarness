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
    agent_ids: list[str]
    agent_names: dict[str, str]
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
    agent_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    broadcasts: list[dict[str, Any]] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        primary = self.agent_states.get(self.agent_id, {})
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_ids": self.agent_ids,
            "agents": [self.agent_states[agent_id] for agent_id in self.agent_ids],
            "session_date": self.session_date,
            "mode": self.mode,
            "initial_cash": self.initial_cash,
            "clock_state": self.clock_state,
            "phase": self.phase,
            "error": self.error,
            "event_count": len(self.events),
            "account": primary.get("account", self.account),
            "positions": primary.get("positions", self.positions),
            "trades": primary.get("trades", self.trades),
            "equity_curve": primary.get("equity_curve", self.equity_curve),
            "quote_health": self.quote_health,
            "broadcasts": self.broadcasts[-100:],
            "last_event": self.last_event,
        }


PaperRunnerFactory = Callable[[Any, str, list[dict[str, Any]]], Any]


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
        cards = []
        for agent_id in request.agent_ids:
            card = load_card(agent_id, storage_dir=self._agent_root) or load_card(agent_id)
            if card is None:
                raise ValueError(f"未找到智能体卡片：{agent_id}")
            cards.append(card)
        session_id = uuid.uuid4().hex
        card_payloads = [card.to_dict() for card in cards]
        runner = self._runner_factory(request, session_id, card_payloads)
        agent_states = {
            card.id: {
                "agent_id": card.id,
                "agent_name": card.name,
                "model": card.model,
                "status": "queued",
                "phase": "pre_market",
                "account": {
                    "cash": float(request.initial_cash),
                    "equity": float(request.initial_cash),
                    "return_pct": 0.0,
                },
                "positions": [],
                "trades": [],
                "equity_curve": [],
                "last_event": None,
                "error": None,
            }
            for card in cards
        }
        primary = cards[0]
        managed = _ManagedPaper(
            id=session_id,
            runner=runner,
            created_at=datetime.now(timezone.utc).isoformat(),
            agent_id=primary.id,
            agent_name=primary.name,
            agent_ids=[card.id for card in cards],
            agent_names={card.id: card.name for card in cards},
            session_date=request.session_date,
            mode=request.mode,
            initial_cash=float(request.initial_cash),
            account={
                "cash": float(request.initial_cash),
                "equity": float(request.initial_cash),
                "return_pct": 0.0,
            },
            agent_states=agent_states,
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
            for state in managed.agent_states.values():
                if state.get("status") not in {"failed", "cancelled"}:
                    state["status"] = managed.status
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
            agent_id = str(data.get("agent_id") or managed.agent_id)
            agent_state = managed.agent_states.get(agent_id)
            if agent_state is not None:
                agent_state["last_event"] = document
            if event.type == "phase_change":
                managed.phase = str(data.get("phase", managed.phase))
                managed.clock_state = "agent_working"
                if agent_state is not None:
                    agent_state["phase"] = managed.phase
                    agent_state["status"] = "running"
            elif event.type == "paper_clock":
                managed.phase = str(data.get("phase", managed.phase))
                managed.clock_state = str(data.get("state", managed.clock_state))
                if agent_state is not None:
                    current_index = managed.agent_ids.index(agent_id)
                    for completed_id in managed.agent_ids[:current_index]:
                        completed = managed.agent_states[completed_id]
                        if completed.get("status") == "running":
                            completed["status"] = "done"
                    agent_state["phase"] = managed.phase
                    agent_state["status"] = "running"
            elif event.type == "paper_quote":
                managed.quote_health = {
                    "source": data.get("source"),
                    "missing_codes": data.get("missing_codes", []),
                    "request_metrics": data.get("request_metrics", {}),
                    "as_of": data.get("as_of"),
                    "attention_codes": data.get("attention_codes", []),
                    "one_minute_bars": data.get("one_minute_bars", 0),
                }
                if agent_state is not None:
                    agent_state["quote_health"] = dict(managed.quote_health)
            elif event.type == "paper_snapshot":
                account = dict(data.get("account") or {})
                positions = list(data.get("positions") or [])
                trades = list(data.get("trades") or [])
                managed.account = account
                managed.positions = positions
                managed.trades = trades
                managed.quote_health.update(data.get("quote_health") or {})
                observed_at = str(data.get("observed_at") or event.ts)
                equity = account.get("equity")
                if equity is not None:
                    point = [observed_at, float(equity)]
                    if not managed.equity_curve or managed.equity_curve[-1] != point:
                        managed.equity_curve.append(point)
                    if agent_state is not None:
                        curve = agent_state.setdefault("equity_curve", [])
                        if not curve or curve[-1] != point:
                            curve.append(point)
                if agent_state is not None:
                    agent_state["account"] = account
                    agent_state["positions"] = positions
                    agent_state["trades"] = trades
                    agent_state["phase"] = str(data.get("phase", agent_state["phase"]))
            elif event.type in {"paper_market_pulse", "paper_news"}:
                managed.broadcasts.append(document)
            elif event.type == "error":
                managed.error = str(data.get("message") or data.get("error") or "模拟盘错误")
                if agent_state is not None:
                    agent_state["status"] = "failed"
                    agent_state["error"] = managed.error
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
                primary_id = str(state["agent_id"])
                stored_agents = list(state.get("agents") or [])
                agent_ids = [str(value) for value in state.get("agent_ids") or []]
                if not agent_ids:
                    agent_ids = [str(item.get("agent_id")) for item in stored_agents if item.get("agent_id")]
                if not agent_ids:
                    agent_ids = [primary_id]
                agent_states = {
                    str(item["agent_id"]): dict(item)
                    for item in stored_agents
                    if item.get("agent_id")
                }
                if primary_id not in agent_states:
                    agent_states[primary_id] = {
                        "agent_id": primary_id,
                        "agent_name": str(state.get("agent_name", primary_id)),
                        "model": "",
                        "status": status,
                        "phase": str(state.get("phase", "pre_market")),
                        "account": dict(state.get("account") or {}),
                        "positions": list(state.get("positions") or []),
                        "trades": list(state.get("trades") or []),
                        "equity_curve": list(state.get("equity_curve") or []),
                        "last_event": state.get("last_event"),
                        "error": error,
                    }
                if status == "failed" and state.get("status") in {"running", "cancelling"}:
                    for item in agent_states.values():
                        if item.get("status") not in {"done", "cancelled"}:
                            item["status"] = "failed"
                            item["error"] = error
                managed = _ManagedPaper(
                    id=str(state["id"]),
                    runner=None,
                    created_at=str(state["created_at"]),
                    agent_id=primary_id,
                    agent_name=str(state.get("agent_name", primary_id)),
                    agent_ids=agent_ids,
                    agent_names={
                        agent_id: str(agent_states[agent_id].get("agent_name", agent_id))
                        for agent_id in agent_ids
                    },
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
                    agent_states=agent_states,
                    broadcasts=list(state.get("broadcasts") or []),
                )
                self._sessions[managed.id] = managed
                if status == "failed" and state.get("status") in {"running", "cancelling"}:
                    self._persist_state(managed)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def _build_runner(
        self,
        request: Any,
        session_id: str,
        agents: list[dict[str, Any]],
    ):
        return PaperTradingRunner(
            PaperRunConfig(
                session_id=session_id,
                agents=agents,
                session_date=datetime.fromisoformat(request.session_date).date(),
                initial_cash=float(request.initial_cash),
                mode=request.mode,
                poll_seconds=int(request.poll_seconds),
                max_attention_codes=int(request.max_attention_codes),
                dataset_root=self._dataset_root,
                artifact_root=self._session_root(session_id),
            )
        )
