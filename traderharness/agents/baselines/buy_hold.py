"""BuyAndHold baseline agent."""

from __future__ import annotations

from datetime import date


class BuyHoldAgent:
    """Buys equal weight on day 1, holds forever."""

    def __init__(self, agent_id: str = "buy_hold", stock_codes: list[str] | None = None):
        self.agent_id = agent_id
        self.name = "BuyAndHold"
        self._stock_codes = stock_codes or []
        self._bought = False

    async def on_day(self, env, current_date: date) -> None:
        if self._bought:
            return
        if not self._stock_codes:
            return
        for code in self._stock_codes:
            env.place_order(
                agent_id=self.agent_id,
                stock_code=code,
                side="buy",
                quantity=100,
            )
        self._bought = True
