"""Backtest Detail page — equity curve, trades, decision replay."""

from __future__ import annotations


def render():
    import streamlit as st

    st.title("Backtest Detail")

    tab1, tab2, tab3 = st.tabs(["Equity Curve", "Trades", "Decision Replay"])

    with tab1:
        st.markdown("### Equity Curve")
        st.info("Select a completed run from Dashboard to view equity curve.")

    with tab2:
        st.markdown("### Trade History")
        st.info("Trade table will appear here after a run completes.")

    with tab3:
        st.markdown("### Decision Replay")
        st.info("Step-by-step replay of agent decisions.")
        st.markdown("""
        - View each day's analysis
        - See tool calls and reasoning
        - Inspect portfolio state at each step
        """)
