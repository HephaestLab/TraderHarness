"""Trajectory page — step-level analysis."""

from __future__ import annotations


def render():
    import streamlit as st

    st.title("Trajectory Analysis")

    st.markdown("### Day-Level Records (RL Format)")
    st.info("obs / actions / reward / done — for RL training pipelines")

    st.markdown("### Step-Level Records")
    st.info("Fine-grained: each LLM call, tool invocation, and reasoning step")

    st.markdown("### Export")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Export Day Parquet")
    with col2:
        st.button("Export Step Parquet")
