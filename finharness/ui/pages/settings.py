"""Settings page — configuration editor."""

from __future__ import annotations


def render():
    import streamlit as st

    st.title("Settings")

    st.markdown("### Environment")
    st.text_input("Data Directory", value="./data")
    st.checkbox("Enable SQLite Cache", value=True)
    st.selectbox("Log Level", ["DEBUG", "INFO", "WARNING", "ERROR"])

    st.markdown("### LLM Configuration")
    st.text_input("Model", value="deepseek-chat")
    st.text_input("API Key (env var name)", value="DEEPSEEK_API_KEY")
    st.slider("Temperature", 0.0, 1.0, 0.7)

    st.markdown("### Backtest Defaults")
    st.number_input("Default Initial Cash", value=1_000_000)
    st.number_input("Warmup Days", value=60)

    if st.button("Save Settings"):
        st.success("Settings saved (would write to config file)")
