"""Dashboard page — run configuration + real-time monitoring."""

from __future__ import annotations


def render():
    import streamlit as st

    st.title("Dashboard")
    st.markdown("### Run Configuration")

    col1, col2 = st.columns(2)
    with col1:
        agent_config = st.file_uploader("Agent YAML", type=["yaml", "yml"])
        dataset = st.selectbox("Dataset", ["a50-2024", "a50-2023", "test-fixture"])
    with col2:
        initial_cash = st.number_input("Initial Cash (¥)", value=1_000_000, step=100_000)
        runs = st.number_input("Number of Runs", value=1, min_value=1, max_value=100)

    if st.button("Start Backtest", type="primary"):
        with st.spinner("Running backtest..."):
            st.info("Backtest execution would happen here")

    st.markdown("---")
    st.markdown("### Recent Runs")
    st.info("No runs yet. Configure and start a backtest above.")
