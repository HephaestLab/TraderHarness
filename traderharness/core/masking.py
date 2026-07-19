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

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar

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
    _text_date_re: ClassVar[re.Pattern] = re.compile(
        r"(?<!\d)(?P<year>20\d{2})(?:年|[-/])"
        r"(?P<month>1[0-2]|0?[1-9])(?:月|[-/])(?P<day>3[01]|[12]\d|0?[1-9])日?"
        r"(?:[ T](?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?)?(?!\d)"
    )
    # Year-month only: Chinese form requires 月; ISO form uses - or /.
    # Month is constrained to 1–12 so copy like "2024年15个百分点" is left alone.
    _text_month_re: ClassVar[re.Pattern] = re.compile(
        r"(?<!\d)(?P<year>20\d{2})"
        r"(?:"
        r"年(?P<month_cn>1[0-2]|0?[1-9])月"
        r"|"
        r"[-/](?P<month_iso>1[0-2]|0?[1-9])(?![-/\d])"
        r")"
    )
    _text_month_day_re: ClassVar[re.Pattern] = re.compile(
        r"(?<![\d年])(?P<month>1[0-2]|0?[1-9])月"
        r"(?P<day>3[01]|[12]\d|0?[1-9])日"
    )

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

    def mask_text(self, value: Any) -> Any:
        """Replace absolute full dates embedded in free text."""
        if not self.enabled or not isinstance(value, str):
            return value

        def replace(match: re.Match) -> str:
            try:
                day = date(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            except ValueError:
                return match.group(0)
            if match.group("hour") is None:
                return self.mask_date(day)
            timestamp = datetime.combine(
                day,
                datetime.min.time(),
            ).replace(
                hour=int(match.group("hour")),
                minute=int(match.group("minute")),
            )
            return self.mask_datetime(timestamp)

        text = self._text_date_re.sub(replace, value)

        def replace_month_day(match: re.Match) -> str:
            month = int(match.group("month"))
            day = int(match.group("day"))
            candidates = []
            for year in range(self.anchor.year - 1, self.anchor.year + 2):
                try:
                    candidates.append(date(year, month, day))
                except ValueError:
                    continue
            if not candidates:
                return match.group(0)
            nearest = min(
                candidates,
                key=lambda candidate: abs((candidate - self.anchor).days),
            )
            return self.mask_date(nearest)

        text = self._text_month_day_re.sub(replace_month_day, text)

        def replace_month(match: re.Match) -> str:
            month_raw = match.group("month_cn") or match.group("month_iso")
            try:
                first_day = date(int(match.group("year")), int(month_raw), 1)
            except (TypeError, ValueError):
                return match.group(0)
            return f"{self.mask_date(first_day)}所在月"

        return self._text_month_re.sub(replace_month, text)

    def mask_obj(self, value: Any) -> Any:
        """Mask absolute dates embedded in nested Agent-visible text."""
        if not self.enabled:
            return value
        if isinstance(value, (datetime, pd.Timestamp)):
            return self.mask_datetime(value)
        if isinstance(value, date):
            return self.mask_date(value)
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, dict):
            return {key: self.mask_obj(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.mask_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.mask_obj(item) for item in value)
        return value

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
