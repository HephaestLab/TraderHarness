"""traderharness_api — sandboxed data gateway for execute_code tool.

All data access goes through this module which enforces date masking.
Agent code: `from traderharness_api import market, portfolio, news`
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from traderharness.tools.registry import ToolContext


# Latest minute-of-day the agent is allowed to see, per sub-window / phase.
# Anything later hasn't "happened yet" for the current decision point.
_SUB_WINDOW_CAP = {
    "open_1": 9 * 60 + 50,
    "open_2": 10 * 60,
    "close_1": 14 * 60 + 50,
    "close_2": 15 * 60,
}
_PHASE_CAP = {
    "pre_market": 0,  # no intraday data of today is visible pre-open
    "open_window": 10 * 60,
    "close_window": 15 * 60,
}


def _visible_minute_cap(ctx: ToolContext) -> int:
    """Max minute-of-day of 5-min bars visible at the current decision point."""
    sub = getattr(ctx, "_current_sub_window", None)
    if sub in _SUB_WINDOW_CAP:
        return _SUB_WINDOW_CAP[sub]
    return _PHASE_CAP.get(ctx.current_phase, 0)


def _mask_df(ctx: ToolContext, df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """Apply date and entity masking to an Agent-facing DataFrame."""
    date_masker = getattr(ctx, "date_masker", None)
    out = date_masker.mask_df(df, col) if date_masker is not None else df
    entity_masker = getattr(ctx, "entity_masker", None)
    return entity_masker.mask_df(out) if entity_masker is not None else out


def _unmask_code(ctx: ToolContext, code: str) -> str:
    masker = getattr(ctx, "entity_masker", None)
    return masker.unmask_code(code) if masker is not None else code


def _mask_obj(ctx: ToolContext, value):
    masker = getattr(ctx, "entity_masker", None)
    return masker.mask_obj(value) if masker is not None else value


class MarketAPI:
    """Market data gateway with strict date masking."""

    def __init__(self, ctx: ToolContext) -> None:
        self._ctx = ctx

    def get_kline(self, code: str, days: int = 60) -> pd.DataFrame:
        """Get daily OHLCV for a single stock (masked to before current_date)."""
        code = _unmask_code(self._ctx, code)
        df = self._ctx.preloaded_daily.get(code)
        if df is None or df.empty:
            return pd.DataFrame()
        filtered = df[df["date"] < self._ctx.current_date].tail(days).reset_index(drop=True)
        return _mask_df(self._ctx, filtered)

    def get_kline_5min(self, code: str) -> pd.DataFrame:
        """Get today's 5-minute bars (only bars already elapsed at this decision point)."""
        code = _unmask_code(self._ctx, code)
        bars = self._ctx.window_minutes.get(code)
        if bars is None or (hasattr(bars, "empty") and bars.empty):
            bus = getattr(self._ctx, "_bus", None)
            if bus is not None:
                bars = bus.get_5min_bars(code, self._ctx.current_date)
        if bars is None or bars.empty:
            return pd.DataFrame()
        cap = _visible_minute_cap(self._ctx)
        if "datetime" in bars.columns:
            minutes = bars["datetime"].dt.hour * 60 + bars["datetime"].dt.minute
            bars = bars[minutes <= cap].reset_index(drop=True)
            masker = getattr(self._ctx, "date_masker", None)
            if masker is not None and masker.enabled and not bars.empty:
                # Keep wall-clock time, neutralize the calendar date.
                bars = bars.copy()
                bars["datetime"] = pd.to_datetime(
                    bars["datetime"].dt.strftime("2000-01-01 %H:%M:%S")
                )
            return _mask_df(self._ctx, bars)
        if cap <= 0:
            return pd.DataFrame()
        return _mask_df(self._ctx, bars.reset_index(drop=True))

    def get_stock_list(self) -> list[str]:
        """Get all available stock codes."""
        return _mask_obj(self._ctx, list(self._ctx.preloaded_daily.keys()))

    def get_all_stocks(self) -> list[str]:
        """Compatibility alias for get_stock_list()."""
        return self.get_stock_list()

    def get_all_daily(self, days: int = 20, **kwargs) -> pd.DataFrame:
        """Get all-market recent N days as a single DataFrame.

        Returns columns: stock_code, date, open, high, low, close, volume, change_pct.
        ``change_pct`` is vs the previous visible bar of the same stock (NaN on
        the first bar in the returned window).
        """
        if kwargs:
            illegal = ", ".join(sorted(kwargs))
            raise TypeError(
                f"get_all_daily() only accepts days= (got: {illegal}). "
                "Fetch with days=N then filter by the integer date column yourself; "
                "offset/date_offset are not supported."
            )
        days = min(max(int(days), 1), 120)
        frames = []
        for code, df in self._ctx.preloaded_daily.items():
            if df is None or df.empty:
                continue
            filtered = df[df["date"] < self._ctx.current_date].tail(days)
            if filtered.empty:
                continue
            chunk = filtered.copy()
            chunk["stock_code"] = code
            closes = chunk["close"].astype(float)
            chunk["change_pct"] = (closes / closes.shift(1) - 1.0) * 100.0
            frames.append(chunk)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        if "change_pct" in out.columns:
            out["change_pct"] = out["change_pct"].round(2)
        return _mask_df(self._ctx, out)

    def get_market_overview(self) -> dict:
        """Full-market breadth and sector leaders (point-in-time)."""
        from traderharness.tools.analysis import build_market_overview

        return _mask_obj(self._ctx, build_market_overview(self._ctx))

    def get_sector_summary(self, sector: str) -> dict:
        """Sector average change and ranked constituents (point-in-time)."""
        from traderharness.tools.analysis import build_sector_summary

        return _mask_obj(self._ctx, build_sector_summary(self._ctx, sector))

    def get_sector_stocks(self, sector: str) -> pd.DataFrame:
        """Sector constituents as a DataFrame: stock_code, close, change_pct."""
        from traderharness.tools.analysis import build_sector_constituents

        stocks = build_sector_constituents(self._ctx, sector)
        if isinstance(stocks, dict):
            return pd.DataFrame()
        rows = [
            {
                "stock_code": item["code"],
                "close": item["close"],
                "change_pct": item["change_pct"],
            }
            for item in stocks
        ]
        return _mask_df(self._ctx, pd.DataFrame(rows))

    def screen_stocks(self, **kwargs) -> dict:
        """Condition screen — same parameters as the screen_stocks tool."""
        from traderharness.tools.analysis import build_screen_stocks

        return _mask_obj(self._ctx, build_screen_stocks(self._ctx, kwargs))

    def get_stock_price(self, code: str) -> dict:
        """Latest visible daily quote and 1-day change (before current_date)."""
        code = _unmask_code(self._ctx, code)
        df = self._ctx.preloaded_daily.get(code)
        if df is None or df.empty:
            return _mask_obj(self._ctx, {"error": f"无法获取 {code} 的行情数据"})
        filtered = df[df["date"] < self._ctx.current_date]
        if filtered.empty:
            return _mask_obj(self._ctx, {"error": f"{code} 在当前交易日之前无数据"})
        last = filtered.iloc[-1]
        prev = filtered.iloc[-2] if len(filtered) >= 2 else last
        prev_close = float(prev["close"])
        change_pct = (
            ((float(last["close"]) - prev_close) / prev_close * 100) if prev_close != 0 else 0.0
        )
        masker = getattr(self._ctx, "date_masker", None)
        day_label = masker.mask_date(last["date"]) if masker is not None else "T-1"
        return _mask_obj(
            self._ctx,
            {
                "stock_code": code,
                "day": day_label,
                "open": round(float(last["open"]), 2),
                "high": round(float(last["high"]), 2),
                "low": round(float(last["low"]), 2),
                "close": round(float(last["close"]), 2),
                "volume": int(last.get("volume", 0)),
                "change_pct": round(change_pct, 2),
            },
        )

    def get_fundamentals(self, code: str) -> dict | None:
        """Get latest fundamentals visible before current_date."""
        code = _unmask_code(self._ctx, code)
        fund_data = self._ctx.tool_call_cache.get("_fundamentals_data")
        if fund_data is None or fund_data.empty:
            return None
        stock_data = fund_data[
            (fund_data["stock_code"] == code)
            & (fund_data["pub_date"] <= str(self._ctx.current_date))
        ]
        if stock_data.empty:
            return None
        latest = stock_data.iloc[-1].to_dict()
        masker = getattr(self._ctx, "date_masker", None)
        if masker is not None and "pub_date" in latest:
            latest["pub_date"] = masker.mask_date(latest["pub_date"])
        return _mask_obj(self._ctx, latest)


class PortfolioAPI:
    """Read-only portfolio access."""

    def __init__(self, ctx: ToolContext) -> None:
        self._ctx = ctx

    def get_positions(self) -> list[dict]:
        """Get current positions as list of dicts."""
        results = []
        for code, pos in self._ctx.portfolio.positions.items():
            results.append(
                {
                    "stock_code": code,
                    "quantity": pos.quantity,
                    "avg_cost": float(pos.avg_cost),
                    "market_value": float(pos.avg_cost) * pos.quantity,
                }
            )
        return _mask_obj(self._ctx, results)

    def get_cash(self) -> float:
        """Get available cash."""
        return float(self._ctx.portfolio.cash)

    def get_total_value(self) -> float:
        """Get total portfolio value at current prices."""
        prices = self._ctx.execution_price
        return float(self._ctx.portfolio.total_value(prices)) if prices else self.get_cash()


class NewsAPI:
    """News and announcement access with date masking."""

    def __init__(self, ctx: ToolContext) -> None:
        self._ctx = ctx

    def get_announcements(self, code: str, days: int = 30) -> list[dict]:
        """Get recent announcements for a stock."""
        from datetime import timedelta

        code = _unmask_code(self._ctx, code)
        ann_data = self._ctx.tool_call_cache.get("_announcements_data")
        if ann_data is None or ann_data.empty:
            return []
        start = self._ctx.current_date - timedelta(days=days)
        filtered = ann_data[
            (ann_data["stock_code"] == code)
            & (ann_data["announcement_time"].dt.date >= start)
            & (ann_data["announcement_time"].dt.date < self._ctx.current_date)
        ]
        masker = getattr(self._ctx, "date_masker", None)
        results = []
        for _, row in filtered.tail(20).iterrows():
            t = row["announcement_time"]
            results.append(
                {
                    "title": row["title"],
                    "time": masker.mask_datetime(t) if masker is not None else str(t),
                }
            )
        return _mask_obj(self._ctx, results)

    def get_policy_news(self, days: int = 7) -> list[dict]:
        """Get recent policy/national news."""
        from datetime import timedelta

        news_data = self._ctx.tool_call_cache.get("_news_data")
        if news_data is None or news_data.empty:
            return []
        start = self._ctx.current_date - timedelta(days=days)
        keywords = ["央行", "证监会", "国务院", "财政部", "银保监", "发改委", "人民银行"]
        filtered = news_data[
            (news_data["display_time"].dt.date >= start)
            & (news_data["display_time"].dt.date < self._ctx.current_date)
        ]
        if filtered.empty:
            return []
        policy = filtered[filtered["content"].str.contains("|".join(keywords), na=False)]
        masker = getattr(self._ctx, "date_masker", None)
        results = []
        for _, row in policy.tail(20).iterrows():
            t = row["display_time"]
            results.append(
                {
                    "time": masker.mask_datetime(t) if masker is not None else str(t),
                    "content": str(row["content"])[:300],
                }
            )
        return _mask_obj(self._ctx, results)


def build_api_module(ctx: ToolContext) -> dict:
    """Build the traderharness_api namespace dict for sandbox injection."""
    return {
        "market": MarketAPI(ctx),
        "portfolio": PortfolioAPI(ctx),
        "news": NewsAPI(ctx),
    }
