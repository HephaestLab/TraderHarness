"""Random baseline agent — makes random buy/sell decisions."""

from __future__ import annotations

import random
from datetime import date


class RandomAgent:
    """Makes random trading decisions for baseline comparison."""

    def __init__(
        self,
        agent_id: str = "random",
        stock_codes: list[str] | None = None,
        trade_probability: float = 0.3,
        seed: int | None = None,
    ):
        self.agent_id = agent_id
        self.name = "Random"
        self._stock_codes = stock_codes or []
        self._trade_prob = trade_probability
        self._rng = random.Random(seed)

    async def on_day(self, env, current_date: date) -> None:
        if not self._stock_codes:
            return
        if self._rng.random() > self._trade_prob:
            return
        code = self._rng.choice(self._stock_codes)
        side = self._rng.choice(["buy", "sell"])
        env.place_order(
            agent_id=self.agent_id,
            stock_code=code,
            side=side,
            quantity=100,
        )
