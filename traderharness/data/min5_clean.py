"""Canonical cleaning for raw BaoStock and normalized 5-minute bars."""

from __future__ import annotations

from datetime import time as dtime

import pandas as pd

MIN5_COLUMNS = [
    "stock_code",
    "date",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def normalize_datetime(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize full timestamps, BaoStock raw timestamps, or HH:MM:SS."""
    out = frame.copy()
    values = out["datetime"]
    if pd.api.types.is_datetime64_any_dtype(values):
        out["datetime"] = pd.to_datetime(values)
        return out

    text = values.astype(str)
    raw = text.str.len() >= 14
    parsed = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    parsed.loc[raw] = pd.to_datetime(text.loc[raw].str[:14], format="%Y%m%d%H%M%S", errors="coerce")
    if (~raw).any():
        dates = pd.to_datetime(out.loc[~raw, "date"]).dt.strftime("%Y-%m-%d")
        parsed.loc[~raw] = pd.to_datetime(dates + " " + text.loc[~raw], errors="coerce")
    out["datetime"] = parsed
    return out


def clean_min5(frame: pd.DataFrame) -> pd.DataFrame:
    """Return canonical in-session, positive-volume, deduplicated bars."""
    if frame.empty:
        return pd.DataFrame(columns=MIN5_COLUMNS + ["year"])
    out = normalize_datetime(frame)
    out = out[out["datetime"].notna()].copy()
    times = out["datetime"].dt.time
    in_session = ((times >= dtime(9, 30)) & (times <= dtime(11, 30))) | (
        (times >= dtime(13, 0)) & (times <= dtime(15, 0))
    )
    out = out[in_session]
    if "volume" in out.columns:
        out = out[pd.to_numeric(out["volume"], errors="coerce").fillna(0) > 0]
    out["date"] = pd.to_datetime(out["datetime"].dt.date)
    for column in MIN5_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    out = out[MIN5_COLUMNS].drop_duplicates(["stock_code", "datetime"], keep="last")
    out["year"] = out["datetime"].dt.year.astype(int)
    return out.reset_index(drop=True)
