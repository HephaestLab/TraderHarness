"""Trade history table component."""

from __future__ import annotations


def render_trade_table(trades: list[dict]):
    """Render trade history as a table."""
    import pandas as pd
    import streamlit as st

    if not trades:
        st.info("No trades recorded.")
        return

    df = pd.DataFrame(trades)
    display_cols = ["trade_date", "action", "stock_code", "price", "quantity", "amount"]
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], use_container_width=True)
