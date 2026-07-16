"""TDD tests for intraday 5-min look-ahead protection (洞2).

The agent-facing 5-min view must only expose bars that have already elapsed for
the current phase / sub-window. At pre-market it must expose nothing of today;
in the open window only bars up to 10:00; etc.
"""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.tools.registry import ToolContext
from traderharness.core.portfolio import Portfolio
from traderharness.agents.sandbox.api import MarketAPI


def _full_day_bars() -> pd.DataFrame:
    times = ["09:35", "09:50", "09:55", "10:00", "14:30", "14:50", "15:00"]
    return pd.DataFrame({
        "datetime": [datetime(2024, 3, 5, int(t[:2]), int(t[3:])) for t in times],
        "date": [date(2024, 3, 5)] * len(times),
        "close": [100 + i for i in range(len(times))],
    })


def _make_ctx(phase: str, sub_window: str | None = None) -> ToolContext:
    ctx = ToolContext(
        current_date=date(2024, 3, 5),
        current_phase=phase,
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        window_minutes={"600519": _full_day_bars()},
        agent_id="t",
        workspace_root="t",
    )
    if sub_window is not None:
        ctx._current_sub_window = sub_window
    return ctx


def _minutes(df: pd.DataFrame) -> list[int]:
    return [dt.hour * 60 + dt.minute for dt in df["datetime"]]


class TestFiveMinWindowMasking:
    def test_premarket_sees_nothing(self):
        api = MarketAPI(_make_ctx("pre_market"))
        df = api.get_kline_5min("600519")
        assert df.empty

    def test_open_window_caps_at_10am(self):
        api = MarketAPI(_make_ctx("open_window", "open_2"))
        df = api.get_kline_5min("600519")
        assert len(df) == 4  # 9:35, 9:50, 9:55, 10:00
        assert max(_minutes(df)) <= 10 * 60

    def test_open_1_caps_at_950(self):
        api = MarketAPI(_make_ctx("open_window", "open_1"))
        df = api.get_kline_5min("600519")
        assert max(_minutes(df)) <= 9 * 60 + 50
        # the 9:55 / 10:00 bars must NOT be visible yet
        assert (9 * 60 + 55) not in _minutes(df)

    def test_close_1_caps_at_1450(self):
        api = MarketAPI(_make_ctx("close_window", "close_1"))
        df = api.get_kline_5min("600519")
        assert max(_minutes(df)) <= 14 * 60 + 50
        assert (15 * 60) not in _minutes(df)

    def test_close_2_sees_full_day(self):
        api = MarketAPI(_make_ctx("close_window", "close_2"))
        df = api.get_kline_5min("600519")
        assert len(df) == 7
