"""AgentProtocol — the interface all agents must implement."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from traderharness.core.engine import TradingBus


@runtime_checkable
class AgentProtocol(Protocol):
    """Any agent that can be run by the BacktestEngine."""

    agent_id: str
    name: str

    async def on_day(self, env: TradingBus, current_date: date) -> None:
        """Called once per trading day. Agent uses env to query data and trade."""
        ...
