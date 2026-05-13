"""Equity curve chart component."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def render_equity_curve(equity_curve: list[tuple[date, Decimal]], title: str = "Equity Curve"):
    """Render equity curve using plotly."""
    import plotly.graph_objects as go
    import streamlit as st

    dates = [d for d, _ in equity_curve]
    values = [float(v) for _, v in equity_curve]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=values, mode="lines", name="Portfolio Value"))
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Value (¥)")
    st.plotly_chart(fig, use_container_width=True)
