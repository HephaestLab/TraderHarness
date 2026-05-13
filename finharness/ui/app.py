"""Streamlit main entry point for FinHarness UI."""

from __future__ import annotations


def main():
    import streamlit as st

    st.set_page_config(page_title="FinHarness", page_icon="📈", layout="wide")

    page = st.sidebar.selectbox(
        "Navigation",
        ["Dashboard", "Backtest Detail", "Trajectory", "Settings"],
    )

    if page == "Dashboard":
        from finharness.ui.pages.dashboard import render
        render()
    elif page == "Backtest Detail":
        from finharness.ui.pages.backtest_detail import render
        render()
    elif page == "Trajectory":
        from finharness.ui.pages.trajectory import render
        render()
    elif page == "Settings":
        from finharness.ui.pages.settings import render
        render()


if __name__ == "__main__":
    main()
