"""DateMasker — anonymizes real calendar dates shown to the agent.

Scheme B (relative-to-today, calendar-day offset):
  anchor = current_date = today = ``D+0``; visible past data is negative.
  A real date ``d`` renders as ``f"D{(d - anchor).days:+d}"`` (e.g. ``D-21``).
  Datetimes keep their wall-clock time: ``D-6 10:30``.
  Sandbox DataFrame ``date`` columns become integer offsets (same axis).

The masker is presentation-only: the engine keeps real dates internally and the
masker is applied at the agent-facing egress. When ``enabled=False`` every
method returns the real value (bright mode), enabling bright-vs-blinded
comparison experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    return pd.Timestamp(value).date()


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return pd.Timestamp(value).to_pydatetime()


@dataclass
class DateMasker:
    anchor: date
    enabled: bool = True

    def _offset(self, value: Any) -> int:
        return (_to_date(value) - self.anchor).days

    def mask_date(self, value: Any) -> Any:
        """Real date -> ``"D-21"`` (enabled) or the real ISO string (disabled)."""
        if value is None:
            return None
        if not self.enabled:
            return str(value)
        return f"D{self._offset(value):+d}"

    def mask_datetime(self, value: Any) -> Any:
        """Real datetime -> ``"D-6 10:30"`` (enabled) or the real string (disabled)."""
        if value is None:
            return None
        if not self.enabled:
            return str(value)
        dt = _to_datetime(value)
        return f"D{(dt.date() - self.anchor).days:+d} {dt.strftime('%H:%M')}"

    def mask_offset(self, value: Any) -> int:
        """Integer calendar-day offset from today (negative for past)."""
        return self._offset(value)

    def mask_series(self, series: pd.Series) -> pd.Series:
        """Vectorized integer offsets for a Series of dates."""
        dates = pd.to_datetime(series)
        anchor_ts = pd.Timestamp(self.anchor)
        return (dates.dt.normalize() - anchor_ts.normalize()).dt.days

    def mask_df(self, df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
        """Return a copy with ``col`` replaced by integer offsets (no-op if disabled)."""
        if not self.enabled or col not in df.columns:
            return df
        out = df.copy()
        out[col] = self.mask_series(out[col]).to_numpy()
        return out
