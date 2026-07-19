"""EventBus — lightweight publish/subscribe hook system."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Simple event bus supporting on/off/once/emit."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._once_handlers: set[int] = set()

    def on(self, event: str, handler: Callable) -> None:
        self._handlers[event].append(handler)

    def once(self, event: str, handler: Callable) -> None:
        self._handlers[event].append(handler)
        self._once_handlers.add(id(handler))

    def off(self, event: str, handler: Callable) -> None:
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)
            self._once_handlers.discard(id(handler))

    def emit(self, event: str, **kwargs) -> None:
        handlers = self._handlers.get(event)
        if not handlers:
            return
        to_remove = []
        for handler in list(handlers):
            try:
                handler(**kwargs)
            except Exception:
                logger.exception("EventBus handler error on '%s'", event)
            if id(handler) in self._once_handlers:
                to_remove.append(handler)
        for h in to_remove:
            handlers.remove(h)
            self._once_handlers.discard(id(h))
