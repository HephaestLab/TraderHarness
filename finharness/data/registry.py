"""Stock registry — maps codes to metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StockInfo:
    code: str
    name: str
    market: str = ""
    industry: str = ""


class StockRegistry:
    """In-memory stock registry."""

    def __init__(self) -> None:
        self._stocks: dict[str, StockInfo] = {}

    def register(self, info: StockInfo) -> None:
        self._stocks[info.code] = info

    def get(self, code: str) -> StockInfo | None:
        return self._stocks.get(code)

    def all(self) -> list[StockInfo]:
        return list(self._stocks.values())

    def codes(self) -> list[str]:
        return list(self._stocks.keys())

    def load_from_list(self, stocks: list[dict]) -> None:
        for s in stocks:
            self._stocks[s["code"]] = StockInfo(
                code=s["code"],
                name=s.get("name", s["code"]),
                market=s.get("market", ""),
                industry=s.get("industry", ""),
            )

    def __len__(self) -> int:
        return len(self._stocks)

    def __contains__(self, code: str) -> bool:
        return code in self._stocks
