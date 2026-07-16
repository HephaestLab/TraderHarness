"""LiveFeed — thread-safe event stream from backtest engine to UI consumers.

Usage:
    feed = LiveFeed()
    engine = BacktestEngine(config, event_bus=feed.event_bus)

    # In UI thread:
    for event in feed:
        render(event)

    # Or non-blocking:
    event = feed.get(timeout=0.1)
"""

from __future__ import annotations

import time
import queue
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterator

from traderharness.core.events import EventBus


@dataclass(frozen=True)
class FeedEvent:
    type: str
    ts: float
    data: dict[str, Any] = field(default_factory=dict)


class LiveFeed:
    """Thread-safe bridge between async backtest engine and synchronous UI consumer."""

    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: queue.Queue[FeedEvent] = queue.Queue(maxsize=maxsize)
        self._event_bus = EventBus()
        self._done = False
        self._wire_engine_events()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def done(self) -> bool:
        return self._done

    def _wire_engine_events(self) -> None:
        for event_name in (
            "run_start", "run_end",
            "day_start", "day_end",
            "order_placed", "breakpoint_hit",
        ):
            self._event_bus.on(event_name, self._make_handler(event_name))

    def _make_handler(self, event_type: str):
        def handler(**kwargs):
            self._push(event_type, kwargs)
        return handler

    def _push(self, event_type: str, data: dict[str, Any]) -> None:
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, date):
                cleaned[k] = v.isoformat()
            else:
                cleaned[k] = v
        event = FeedEvent(type=event_type, ts=time.time(), data=cleaned)
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass
        if event_type == "run_end":
            self._done = True

    def push(self, event_type: str, **data: Any) -> None:
        self._push(event_type, data)

    def get(self, timeout: float = 0.1) -> FeedEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> FeedEvent | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def drain(self, max_events: int = 100) -> list[FeedEvent]:
        events = []
        for _ in range(max_events):
            ev = self.get_nowait()
            if ev is None:
                break
            events.append(ev)
        return events

    def __iter__(self) -> Iterator[FeedEvent]:
        while not self._done:
            ev = self.get(timeout=0.5)
            if ev is not None:
                yield ev
        while True:
            ev = self.get_nowait()
            if ev is None:
                break
            yield ev
