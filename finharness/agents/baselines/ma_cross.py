"""MACross baseline agent — moving average crossover strategy."""

from __future__ import annotations

from datetime import date


class MACrossAgent:
    """Simple MA crossover: buy when short MA > long MA, sell otherwise."""

    def __init__(
        self,
        agent_id: str = "ma_cross",
        stock_codes: list[str] | None = None,
        short_period: int = 5,
        long_period: int = 20,
    ):
        self.agent_id = agent_id
        self.name = "MACross"
        self._stock_codes = stock_codes or []
        self._short = short_period
        self._long = long_period
        self._price_history: dict[str, list[float]] = {}

    async def on_day(self, env, current_date: date) -> None:
        for code in self._stock_codes:
            if code not in self._price_history:
                self._price_history[code] = []

            price = getattr(env, "_engine", None)
            if hasattr(env, "get_price"):
                p = env.get_price(code)
                if p:
                    self._price_history[code].append(float(p))
            else:
                self._price_history[code].append(0)

            history = self._price_history[code]
            if len(history) < self._long:
                continue

            short_ma = sum(history[-self._short:]) / self._short
            long_ma = sum(history[-self._long:]) / self._long

            if short_ma > long_ma:
                env.place_order(
                    agent_id=self.agent_id,
                    stock_code=code,
                    side="buy",
                    quantity=100,
                )
            elif short_ma < long_ma:
                env.place_order(
                    agent_id=self.agent_id,
                    stock_code=code,
                    side="sell",
                    quantity=100,
                )
