"""TDD tests for DateMasker — relative-to-today calendar-day anonymization (scheme B).

Anchor = current_date = today = D+0. Visible (past) data is negative offset.
Time-of-day is preserved; only the calendar date is anonymized.
When disabled, everything passes through as the real value (bright mode).
"""

from datetime import date, datetime

import pandas as pd

from traderharness.core.masking import DateMasker


ANCHOR = date(2024, 3, 15)  # a Friday


class TestEnabledMasking:
    def test_mask_date_yesterday(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_date(date(2024, 3, 14)) == "D-1"

    def test_mask_date_today_is_d0(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_date(date(2024, 3, 15)) == "D+0"

    def test_mask_date_calendar_offset(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        # 2024-02-23 is 21 calendar days before 2024-03-15
        assert m.mask_date(date(2024, 2, 23)) == "D-21"

    def test_mask_datetime_keeps_time(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_datetime(datetime(2024, 3, 9, 10, 30)) == "D-6 10:30"

    def test_mask_offset_is_int(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_offset(date(2024, 3, 14)) == -1
        assert m.mask_offset(date(2024, 3, 15)) == 0

    def test_accepts_iso_string(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_date("2024-03-14") == "D-1"

    def test_accepts_pandas_timestamp(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_datetime(pd.Timestamp("2024-03-09 10:30:00")) == "D-6 10:30"

    def test_mask_series_vectorized(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        s = pd.Series([date(2024, 3, 13), date(2024, 3, 14)])
        out = list(m.mask_series(s))
        assert out == [-2, -1]

    def test_mask_df_replaces_date_column(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        df = pd.DataFrame({"date": [date(2024, 3, 13), date(2024, 3, 14)], "close": [1.0, 2.0]})
        out = m.mask_df(df, "date")
        assert list(out["date"]) == [-2, -1]
        # original df untouched
        assert df["date"].iloc[0] == date(2024, 3, 13)


class TestDisabledPassthrough:
    def test_mask_date_returns_real(self):
        m = DateMasker(anchor=ANCHOR, enabled=False)
        assert m.mask_date(date(2024, 3, 14)) == "2024-03-14"

    def test_mask_datetime_returns_real(self):
        m = DateMasker(anchor=ANCHOR, enabled=False)
        dt = datetime(2024, 3, 9, 10, 30)
        assert m.mask_datetime(dt) == str(dt)

    def test_mask_df_unchanged(self):
        m = DateMasker(anchor=ANCHOR, enabled=False)
        df = pd.DataFrame({"date": [date(2024, 3, 13)], "close": [1.0]})
        out = m.mask_df(df, "date")
        assert out["date"].iloc[0] == date(2024, 3, 13)


class TestEdgeCases:
    def test_none_passthrough(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        assert m.mask_date(None) is None
        assert m.mask_datetime(None) is None

    def test_missing_date_column_is_noop(self):
        m = DateMasker(anchor=ANCHOR, enabled=True)
        df = pd.DataFrame({"close": [1.0]})
        out = m.mask_df(df, "date")
        assert "close" in out.columns
