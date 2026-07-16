"""DividendManager — handles corporate actions (dividends, bonus shares, suspensions)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd

from traderharness.core.portfolio import Portfolio

logger = logging.getLogger(__name__)

DATASET_DIR = Path.home() / ".finharness" / "dataset"
TWO_PLACES = Decimal("0.01")


class DividendManager:
    """Manages dividend/bonus/transfer actions during backtest."""

    def __init__(self, dataset_dir: Path | None = None) -> None:
        self._dir = dataset_dir or DATASET_DIR
        self._dividends: pd.DataFrame = pd.DataFrame()

    def load(self) -> None:
        path = self._dir / "dividends.parquet"
        if path.exists():
            self._dividends = pd.read_parquet(path)
            if "ex_date" in self._dividends.columns:
                self._dividends["ex_date"] = pd.to_datetime(
                    self._dividends["ex_date"]
                ).dt.date
            logger.info("Dividends loaded: %d rows", len(self._dividends))
        else:
            logger.warning("dividends.parquet not found at %s", path)

    def process_day(
        self, current_date: date, portfolio: Portfolio
    ) -> list[dict]:
        """Process corporate actions for current_date. Returns action log."""
        if self._dividends.empty:
            return []

        actions = []
        today_events = self._dividends[self._dividends["ex_date"] == current_date]

        for _, row in today_events.iterrows():
            code = row["stock_code"]
            if code not in portfolio.positions:
                continue

            pos = portfolio.positions[code]
            original_qty = pos.quantity
            bonus = float(row.get("bonus_shares", 0) or 0)
            transfer = float(row.get("transfer_shares", 0) or 0)
            cash_div = float(row.get("cash_dividend", 0) or 0)

            action = {
                "stock_code": code,
                "type": "corporate_action",
                "date": str(current_date),
                "original_quantity": original_qty,
            }

            # Bonus shares + transfer shares (per 10 shares)
            share_ratio = (bonus + transfer) / 10.0
            if share_ratio > 0:
                new_shares = int(original_qty * share_ratio)
                pos.quantity += new_shares
                # Adjust avg_cost to maintain total cost basis
                if pos.quantity > 0:
                    total_cost = pos.avg_cost * original_qty
                    pos.avg_cost = (total_cost / pos.quantity).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP
                    )
                action["new_shares"] = new_shares
                action["share_ratio"] = share_ratio

            # Cash dividend (per 10 shares, pre-tax)
            if cash_div > 0:
                dividend_amount = Decimal(str(cash_div / 10.0 * original_qty)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                portfolio.cash += dividend_amount
                action["cash_dividend"] = float(dividend_amount)

            desc_parts = []
            if bonus > 0:
                desc_parts.append(f"10送{bonus:.0f}")
            if transfer > 0:
                desc_parts.append(f"10转{transfer:.0f}")
            if cash_div > 0:
                desc_parts.append(f"10派{cash_div:.2f}元")
            action["description"] = "、".join(desc_parts)

            actions.append(action)
            logger.info(
                "Corporate action: %s %s (qty %d→%d)",
                code, action["description"], original_qty, pos.quantity,
            )

        return actions
