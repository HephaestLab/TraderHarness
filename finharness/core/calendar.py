"""TradingCalendar — Chinese A-share trading calendar with holidays."""

from __future__ import annotations

from datetime import date, timedelta


# Chinese market holidays and compensation workdays
# Format: year -> (holidays set, compensation_workdays set)
_CALENDAR_DATA: dict[int, tuple[set[date], set[date]]] = {
    2023: (
        {
            # 元旦
            date(2023, 1, 2),
            # 春节
            date(2023, 1, 23), date(2023, 1, 24), date(2023, 1, 25),
            date(2023, 1, 26), date(2023, 1, 27),
            # 清明
            date(2023, 4, 5),
            # 劳动节
            date(2023, 5, 1), date(2023, 5, 2), date(2023, 5, 3),
            # 端午
            date(2023, 6, 22), date(2023, 6, 23),
            # 中秋+国庆
            date(2023, 9, 29), date(2023, 10, 2), date(2023, 10, 3),
            date(2023, 10, 4), date(2023, 10, 5), date(2023, 10, 6),
        },
        {
            date(2023, 1, 28), date(2023, 1, 29),  # 春节调休
            date(2023, 4, 23), date(2023, 5, 6),   # 劳动节调休
            date(2023, 6, 25),                      # 端午调休
            date(2023, 10, 7), date(2023, 10, 8),   # 国庆调休
        },
    ),
    2024: (
        {
            # 元旦
            date(2024, 1, 1),
            # 春节
            date(2024, 2, 9), date(2024, 2, 12), date(2024, 2, 13),
            date(2024, 2, 14), date(2024, 2, 15), date(2024, 2, 16),
            # 清明
            date(2024, 4, 4), date(2024, 4, 5),
            # 劳动节
            date(2024, 5, 1), date(2024, 5, 2), date(2024, 5, 3),
            # 端午
            date(2024, 6, 10),
            # 中秋
            date(2024, 9, 16), date(2024, 9, 17),
            # 国庆
            date(2024, 10, 1), date(2024, 10, 2), date(2024, 10, 3),
            date(2024, 10, 4), date(2024, 10, 7),
        },
        {
            date(2024, 2, 4), date(2024, 2, 18),   # 春节调休
            date(2024, 4, 7),                       # 清明调休
            date(2024, 4, 28), date(2024, 5, 11),   # 劳动节调休
            date(2024, 9, 14),                      # 中秋调休
            date(2024, 9, 29), date(2024, 10, 12),  # 国庆调休
        },
    ),
    2025: (
        {
            # 元旦
            date(2025, 1, 1),
            # 春节
            date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30),
            date(2025, 1, 31), date(2025, 2, 3), date(2025, 2, 4),
            # 清明
            date(2025, 4, 4),
            # 劳动节
            date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 5),
            # 端午
            date(2025, 5, 30), date(2025, 5, 31),
            # 中秋+国庆
            date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3),
            date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8),
        },
        {
            date(2025, 1, 26), date(2025, 2, 8),   # 春节调休
            date(2025, 4, 27),                      # 劳动节调休
            date(2025, 9, 28), date(2025, 10, 11),  # 国庆调休
        },
    ),
}


class TradingCalendar:
    """Chinese A-share trading calendar.

    A day is a trading day if:
    - It is a weekday (Mon-Fri) AND not a public holiday, OR
    - It is a weekend compensation workday (调休).
    """

    def __init__(self) -> None:
        self._holidays: set[date] = set()
        self._workdays: set[date] = set()
        for _year, (holidays, workdays) in _CALENDAR_DATA.items():
            self._holidays.update(holidays)
            self._workdays.update(workdays)

    def is_trading_day(self, d: date) -> bool:
        if d in self._workdays:
            return True
        if d in self._holidays:
            return False
        return d.weekday() < 5

    def get_trading_days(self, start: date, end: date) -> list[date]:
        days = []
        current = start
        while current <= end:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def next_trading_day(self, d: date) -> date:
        current = d + timedelta(days=1)
        while not self.is_trading_day(current):
            current += timedelta(days=1)
        return current

    def prev_trading_day(self, d: date) -> date:
        current = d - timedelta(days=1)
        while not self.is_trading_day(current):
            current -= timedelta(days=1)
        return current

    def trading_days_between(self, start: date, end: date) -> int:
        return len(self.get_trading_days(start, end))
