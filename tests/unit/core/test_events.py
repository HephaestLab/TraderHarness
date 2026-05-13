"""Tests for EventBus (hook system)."""

import pytest

from finharness.core.events import EventBus


class TestEventBus:
    """Event hook system with on/emit/off."""

    def test_register_and_emit(self):
        bus = EventBus()
        received = []
        bus.on("day_start", lambda **kw: received.append(kw))
        bus.emit("day_start", date="2024-03-04")
        assert len(received) == 1
        assert received[0]["date"] == "2024-03-04"

    def test_multiple_handlers(self):
        bus = EventBus()
        calls = []
        bus.on("run_start", lambda **kw: calls.append("a"))
        bus.on("run_start", lambda **kw: calls.append("b"))
        bus.emit("run_start")
        assert calls == ["a", "b"]

    def test_emit_unknown_event_is_noop(self):
        bus = EventBus()
        bus.emit("nonexistent_event")  # no error

    def test_off_removes_handler(self):
        bus = EventBus()
        calls = []
        handler = lambda **kw: calls.append(1)
        bus.on("day_end", handler)
        bus.off("day_end", handler)
        bus.emit("day_end")
        assert calls == []

    def test_once_fires_only_once(self):
        bus = EventBus()
        calls = []
        bus.once("budget_warn", lambda **kw: calls.append(1))
        bus.emit("budget_warn")
        bus.emit("budget_warn")
        assert calls == [1]

    def test_emit_passes_kwargs(self):
        bus = EventBus()
        received = {}

        def handler(**kw):
            received.update(kw)

        bus.on("order_placed", handler)
        bus.emit("order_placed", stock="600519", action="buy", qty=100)
        assert received == {"stock": "600519", "action": "buy", "qty": 100}

    def test_handler_exception_does_not_break_others(self):
        bus = EventBus()
        calls = []

        def bad_handler(**kw):
            raise RuntimeError("oops")

        bus.on("day_end", bad_handler)
        bus.on("day_end", lambda **kw: calls.append("ok"))
        bus.emit("day_end")
        assert calls == ["ok"]

    def test_builtin_event_names(self):
        """All planned events are supported."""
        bus = EventBus()
        expected = [
            "run_start", "day_start", "order_placed", "day_end",
            "budget_warn", "budget_exhausted", "run_end", "breakpoint_hit",
        ]
        for event in expected:
            bus.emit(event)  # should not error
