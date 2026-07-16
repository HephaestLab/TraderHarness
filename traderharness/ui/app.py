"""TraderHarness — Pixel Art Console.

Pages:
  Dashboard → System status + Select agent + Launch backtest
  Agents    → Agent card gallery + create/edit
  Detail    → Run results (Overview / Timeline / Export)
  Data      → Dataset health
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from traderharness.results import RESULTS_DIR, list_results

# Inline SVG icons (Lucide-style, 16x16)
ICON = {
    "play": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    "bot": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>',
    "db": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    "chart": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    "check": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    "x": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    "clock": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#feca57" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    "plus": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    "edit": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    "trash": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    "download": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "arrow-left": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
}


def _icon(name: str) -> str:
    return f'<span style="display:inline-flex;vertical-align:middle;margin-right:4px;">{ICON.get(name, "")}</span>'


# Agent templates (simplified — no RPG, just persona text)
AGENT_TEMPLATES = [
    {"id": "trend-follower", "name": "Trend Follower", "persona": "你是趋势交易者，只做上升趋势中的股票。价格创新高且量能配合时加仓，跌破关键支撑位立即止损。绝不抄底，趋势在就持有，趋势坏就走人。持仓周期5-15天。"},
    {"id": "value-investor", "name": "Value Investor", "persona": "你是价值投资者，关注低估值、高分红、业绩稳定的龙头公司。很少交易，只在明显低估时重仓买入，长期持有等待价值回归。不追涨杀跌，逆向思维为主。持仓周期通常1-3个月。"},
    {"id": "news-hawk", "name": "News Hawk", "persona": "你擅长从政策公告和新闻中捕捉交易机会。重点关注央行政策、行业利好、个股重大公告。快速反应，消息兑现后立即减仓。持仓周期3-10天。"},
    {"id": "quant-bot", "name": "Quant Bot", "persona": "你是量化交易者，用数据驱动决策。通过技术指标（MACD/KDJ/布林带）、量价关系和统计规律筛选标的。严格止盈止损，不受情绪影响。持仓周期根据信号确定。"},
]


def main():
    import streamlit as st
    from traderharness.ui.theme import inject_theme

    st.set_page_config(page_title="TraderHarness", page_icon="", layout="wide", initial_sidebar_state="expanded")
    inject_theme()

    override = st.session_state.pop("_page_override", None)
    if override:
        st.session_state["_nav_page"] = override
        st.session_state["_nav_radio"] = override

    with st.sidebar:
        st.markdown("# TraderHarness")
        st.caption("v0.1 — Pixel Trading Console")
        st.markdown("---")
        pages = ["Dashboard", "Agents", "Live", "Detail", "Data"]
        current = st.session_state.get("_nav_page", "Dashboard")
        default_idx = pages.index(current) if current in pages else 0
        page = st.radio("NAV", pages, index=default_idx, label_visibility="collapsed", key="_nav_radio")
        st.session_state["_nav_page"] = page
        st.markdown("---")
        _sidebar_recent_runs()

    if page == "Dashboard":
        _page_dashboard()
    elif page == "Agents":
        _page_agents()
    elif page == "Live":
        _page_live()
    elif page == "Detail":
        _page_detail()
    elif page == "Data":
        _page_data()


def _sidebar_recent_runs():
    import streamlit as st
    runs = list_results()
    if not runs:
        return
    st.markdown("### Recent")
    for run in runs[:6]:
        status = run.get("status", "done")
        if status == "running":
            st.button("running...", key=f"sb_{run['file']}", use_container_width=True, disabled=True)
        elif status == "done":
            ret = run.get("return", 0)
            sign = "+" if ret >= 0 else ""
            if st.button(f"{run.get('date','?')} {sign}{ret:.1f}%", key=f"sb_{run['file']}", use_container_width=True):
                st.session_state["selected_run"] = run["file"]
                st.session_state["_nav_page"] = "Detail"
                st.session_state["_page_override"] = "Detail"
                st.rerun()
        else:
            st.button("failed", key=f"sb_{run['file']}", use_container_width=True, disabled=True)


def _load_run(filename: str) -> dict | None:
    path = RESULTS_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

def _page_dashboard():
    import streamlit as st
    from traderharness.agents.agent_card import list_cards

    st.markdown("# DASHBOARD")

    dataset = Path.home() / ".finharness" / "dataset"
    has_daily = (dataset / "daily.parquet").exists()
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market Data", "READY" if has_daily else "MISSING")
    all_runs = list_results()
    done_count = sum(1 for r in all_runs if r.get("status") == "done")
    c2.metric("Runs", str(done_count))
    c3.metric("API Key", "OK" if has_key else "MISSING")
    c4.metric("Agents", str(len(list_cards())))

    st.markdown("---")
    st.markdown("## New Backtest")

    cards = list_cards()

    # Date
    dc1, dc2 = st.columns(2)
    start = dc1.date_input("Start", value=date(2025, 4, 1))
    end = dc2.date_input("End", value=date(2025, 4, 14))

    if start >= end:
        st.error("End date must be after start date.")
        return

    st.markdown("---")

    # Agent picker
    if cards:
        st.markdown("### Select Agent")
        card_names = [c.name for c in cards]
        current_idx = 0
        sel_name = st.selectbox("Agent", card_names, index=current_idx, label_visibility="collapsed")
        sel_card = next(c for c in cards if c.name == sel_name)
        st.caption(f"Model: {sel_card.model} | Cash: {sel_card.initial_cash:,} | Max {sel_card.max_positions} pos")

        with st.expander("Persona preview"):
            st.text(sel_card.persona[:300])

        agent_cfg = {
            "name": sel_card.id,
            "persona": sel_card.persona,
            "max_positions": sel_card.max_positions,
            "max_position_pct": sel_card.max_position_pct,
        }
        cash = sel_card.initial_cash
        model = sel_card.model
    else:
        st.info("No agents yet. Create one in the Agents page, or configure below:")
        agent_name = st.text_input("Agent Name", value="DefaultAgent")
        persona = st.text_area("Persona", value="你是一位经验丰富的主观交易员。", height=80)
        cash = 1_000_000
        model = "deepseek-v4-pro"
        agent_cfg = {"name": agent_name, "persona": persona, "max_positions": 4, "max_position_pct": 25.0}

    st.markdown("---")

    # Start button — show reason if disabled
    if not has_daily:
        st.warning("Market data not found. Run data collection scripts first.")
    if not has_key:
        st.warning("DEEPSEEK_API_KEY not set. Check your .env file.")

    can_start = start < end and has_daily and has_key

    if st.button("START BACKTEST", type="primary", use_container_width=True, disabled=not can_start):
        _start_backtest_subprocess({
            "start_date": str(start),
            "end_date": str(end),
            "initial_cash": cash,
            "model": model,
            "agents": [agent_cfg],
        })


def _start_backtest_subprocess(config: dict):
    """Launch backtest as a background process. UI shows live progress via Live page."""
    import streamlit as st
    import subprocess
    import sys

    agent_cfg = config["agents"][0]

    cmd = [
        sys.executable, "-m", "traderharness.cli", "run",
        "--agent", agent_cfg["name"],
        "--start", config["start_date"],
        "--end", config["end_date"],
        "--cash", str(config["initial_cash"]),
    ]
    if config.get("model"):
        cmd += ["--model", config["model"]]

    subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).parent.parent.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    st.session_state["_nav_page"] = "Live"
    st.session_state["_page_override"] = "Live"
    st.toast("Backtest launched!")
    import time
    time.sleep(0.5)
    st.rerun()


def _page_live():
    """Live view — pixel office + real-time activity feed during backtest."""
    import streamlit as st
    import time as _time

    running = [r for r in list_results() if r.get("status") == "running"]

    if not running:
        from traderharness.ui.components.pet_scene import render_trader_scene
        render_trader_scene(state="sleeping", height=300)
        st.info("No backtest running. Start one from Dashboard.")
        if st.button("Go to Dashboard"):
            st.session_state["_page_override"] = "Dashboard"
            st.rerun()
        return

    run = running[0]

    from traderharness.ui.components.pet_scene import render_trader_scene

    live_path = RESULTS_DIR / run["file"].replace("_result.json", "_live.json")

    if not live_path.exists():
        render_trader_scene(state="waiting", height=300)
        st.markdown(
            "<div style='text-align:center;padding:12px;color:#feca57;'>"
            "Waiting for agent to start...</div>",
            unsafe_allow_html=True,
        )
        _time.sleep(2)
        st.rerun()
        return

    try:
        steps = json.loads(live_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        steps = []

    trader_state = _determine_trader_state(steps)
    render_trader_scene(state=trader_state, height=300)

    # Stats bar + phase indicator
    if steps:
        from collections import defaultdict
        import re

        by_date: dict[str, list] = defaultdict(list)
        for s in steps:
            by_date[s.get("date", "?")].append(s)
        all_dates = sorted(by_date.keys())

        orders = [s for s in steps if s.get("type") == "tool_call" and s.get("data", {}).get("name") == "place_order"]
        buys = sum(1 for o in orders if o.get("data", {}).get("args", {}).get("action") == "buy")
        sells = len(orders) - buys

        # Current phase
        current_phase = "pre_market"
        for s in reversed(steps):
            if s.get("type") == "phase_start":
                current_phase = s.get("data", {}).get("phase", "pre_market")
                break

        phase_labels = {"pre_market": "ANALYSIS", "open_window": "OPEN 9:30-10:00", "close_window": "CLOSE 14:30-15:00"}
        phase_colors = {"pre_market": "#00d2d3", "open_window": "#10b981", "close_window": "#f39c12"}
        phase_label = phase_labels.get(current_phase, current_phase)
        phase_color = phase_colors.get(current_phase, "#7a7a9e")

        st.markdown(
            f"<div style='display:flex;align-items:center;gap:16px;padding:10px 0;font-family:monospace;'>"
            f"<div style='background:{phase_color};color:#000;padding:4px 12px;border-radius:3px;"
            f"font-weight:bold;font-size:0.8rem;'>{phase_label}</div>"
            f"<span style='color:#7a7a9e;font-size:0.8rem;'>DAY <b style=\"color:#fff;\">{len(all_dates)}</b></span>"
            f"<span style='color:#7a7a9e;font-size:0.8rem;'>DATE <b style=\"color:#fff;\">{all_dates[-1]}</b></span>"
            f"<span style='color:#10b981;font-size:0.8rem;'>BUY {buys}</span>"
            f"<span style='color:#ef4444;font-size:0.8rem;'>SELL {sells}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Extract account status from latest morning brief
        latest_equity = None
        initial_cash = None
        ret_pct = None
        for s in steps:
            if s.get("type") == "morning_brief":
                content = s.get("data", {}).get("content", "")
                m = re.search(r"总资产:\s*([\d,]+)", content)
                if m:
                    latest_equity = float(m.group(1).replace(",", ""))
                    if initial_cash is None:
                        initial_cash = latest_equity
                m2 = re.search(r"累计收益:\s*([+\-]?[\d.]+)%", content)
                if m2:
                    ret_pct = float(m2.group(1))

        if latest_equity:
            ret_color = "#10b981" if (ret_pct or 0) >= 0 else "#ef4444"
            ret_str = f"+{ret_pct:.2f}%" if (ret_pct or 0) >= 0 else f"{ret_pct:.2f}%"
            st.markdown(
                f"<div style='display:flex;gap:24px;padding:6px 0;font-family:monospace;font-size:0.8rem;'>"
                f"<span style='color:#7a7a9e;'>EQUITY <b style=\"color:#fff;\">{latest_equity:,.0f}</b></span>"
                f"<span style='color:#7a7a9e;'>RETURN <b style=\"color:{ret_color};\">{ret_str}</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Activity feed — last 20 steps, reverse chronological
        latest_steps = list(reversed(steps[-20:]))
        for i, step in enumerate(latest_steps):
            _render_live_step(step, i)

    st.markdown(
        "<div style='text-align:center;padding:8px;color:#7a7a9e;font-size:0.7rem;'>"
        "Auto-refreshing every 3s</div>",
        unsafe_allow_html=True,
    )
    _time.sleep(3)
    st.rerun()


def _render_live_step(step: dict, idx: int) -> None:
    """Render a single live step with appropriate styling."""
    import streamlit as st

    stype = step.get("type", "")
    sdata = step.get("data", {})
    step_date = step.get("date", "")
    ts_tag = f"<span style='color:#7a7a9e;font-size:0.75rem;margin-right:8px;'>{step_date}</span>"

    if stype == "morning_brief":
        st.markdown(
            f"{ts_tag}<span style='color:#feca57;'>Morning Brief</span>",
            unsafe_allow_html=True,
        )
    elif stype == "phase_start":
        phase = sdata.get("phase", "")
        labels = {"pre_market": "ANALYSIS PHASE", "open_window": "OPEN 9:30-10:00", "close_window": "CLOSE 14:30-15:00"}
        colors = {"pre_market": "#00d2d3", "open_window": "#10b981", "close_window": "#f39c12"}
        color = colors.get(phase, "#7a7a9e")
        label = labels.get(phase, phase)
        st.markdown(
            f"<div style='border-left:3px solid {color};padding:4px 12px;margin:4px 0;'>"
            f"<span style='color:{color};font-weight:bold;font-size:0.8rem;'>{label}</span></div>",
            unsafe_allow_html=True,
        )
    elif stype == "assistant":
        content = sdata.get("content", "")
        if content:
            preview = content[:200].replace("\n", " ")
            with st.expander(f"{step_date} Agent thinking", expanded=(idx == 0)):
                st.markdown(content[:800])
    elif stype == "tool_call":
        name = sdata.get("name", "?")
        args = sdata.get("args", {})
        result = sdata.get("result")

        if name == "place_order":
            action = args.get("action", "")
            code = args.get("stock_code", "")
            qty = args.get("quantity", "")
            price = args.get("price", "")
            reasoning = args.get("reasoning", "")
            is_buy = action == "buy"
            color = "#10b981" if is_buy else "#ef4444"
            icon = "BUY" if is_buy else "SELL"
            st.markdown(
                f"<div style='border-left:3px solid {color};padding:6px 12px;margin:4px 0;"
                f"background:rgba({'16,185,129' if is_buy else '239,68,68'},0.08);border-radius:0 4px 4px 0;'>"
                f"{ts_tag}<span style='color:{color};font-weight:bold;font-size:0.9rem;'>"
                f"{icon}</span> <b>{code}</b> x{qty}"
                f"{'  @' + str(price) if price else ''}"
                f"<br><span style='color:#aaa;font-size:0.75rem;'>{reasoning[:120]}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        elif name == "finish_day":
            summary = args.get("summary", "")
            st.markdown(
                f"<div style='border-left:3px solid #7a7a9e;padding:6px 12px;margin:4px 0;'>"
                f"{ts_tag}<span style='color:#fff;font-weight:bold;'>DAY END</span>"
                f"<br><span style='color:#bbb;font-size:0.8rem;'>{summary[:200]}</span></div>",
                unsafe_allow_html=True,
            )
        else:
            args_preview = json.dumps(args, ensure_ascii=False)[:60]
            label = f"{step_date} {name}({args_preview})"
            with st.expander(label, expanded=False):
                if result:
                    if isinstance(result, dict):
                        st.json(result)
                    else:
                        st.code(str(result)[:2000], language="json")
                else:
                    st.caption("No result data")


def _determine_trader_state(steps: list) -> str:
    """Map backtest live steps to trader animation state."""
    if not steps:
        return "idle"

    last = steps[-1]
    last_type = last.get("type", "")
    last_data = last.get("data", {})

    if last_type == "tool_call":
        name = last_data.get("name", "")
        if name == "place_order":
            return "trading"
        if name == "finish_day":
            return "waiting"
        return "analyzing"

    if last_type == "morning_brief":
        return "analyzing"

    if last_type == "assistant":
        content = last_data.get("content", "").lower()
        if any(w in content for w in ["亏损", "回撤", "止损", "风险"]):
            return "stressed"
        if any(w in content for w in ["盈利", "涨", "收益", "突破"]):
            return "excited"
        return "analyzing"

    if last_type == "phase_start":
        phase = last_data.get("phase", "")
        if phase == "pre_market":
            return "analyzing"
        return "trading"

    return "idle"


# ═══════════════════════════════════════════════════════════════
# AGENTS
# ═══════════════════════════════════════════════════════════════

def _page_agents():
    import streamlit as st
    from traderharness.agents.agent_card import (
        AgentCard, save_card, load_card, list_cards, DEFAULT_STORAGE_DIR,
    )

    st.markdown("# AGENTS")

    cards = list_cards()
    editing_id = st.session_state.get("editing_card")

    # Gallery
    if cards:
        for card in cards:
            is_editing = editing_id == card.id
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.markdown(f"**{card.name}** — `{card.model}` | {card.initial_cash:,} | max {card.max_positions} pos")
            if col2.button("Edit", key=f"e_{card.id}", disabled=is_editing):
                st.session_state["editing_card"] = card.id
                st.session_state.pop("creating_new", None)
                st.rerun()
            if col3.button("Delete", key=f"d_{card.id}"):
                st.session_state["_confirm_delete"] = card.id

        # Delete confirmation
        if st.session_state.get("_confirm_delete"):
            del_id = st.session_state["_confirm_delete"]
            st.warning(f"Delete '{del_id}'?")
            yc, nc, _ = st.columns([1, 1, 4])
            if yc.button("Yes", key="del_y"):
                p = DEFAULT_STORAGE_DIR / f"{del_id}.json"
                if p.exists():
                    p.unlink()
                st.session_state.pop("_confirm_delete", None)
                st.session_state.pop("editing_card", None)
                st.rerun()
            if nc.button("No", key="del_n"):
                st.session_state.pop("_confirm_delete", None)
                st.rerun()

    st.markdown("---")

    # Templates for quick create
    if not editing_id and not st.session_state.get("creating_new"):
        st.markdown("### Create from template")
        tcols = st.columns(len(AGENT_TEMPLATES))
        for i, tmpl in enumerate(AGENT_TEMPLATES):
            with tcols[i]:
                st.markdown(f"**{tmpl['name']}**")
                if st.button("Use", key=f"tmpl_{tmpl['id']}", use_container_width=True):
                    st.session_state["creating_new"] = tmpl
                    st.session_state.pop("editing_card", None)
                    st.rerun()

        if st.button("Create blank"):
            st.session_state["creating_new"] = {"id": "", "name": "", "persona": ""}
            st.session_state.pop("editing_card", None)
            st.rerun()

    # Editor
    creating = st.session_state.get("creating_new")
    if editing_id or creating:
        st.markdown("---")

        if editing_id:
            existing = load_card(editing_id)
            if not existing:
                st.error(f"Card '{editing_id}' not found.")
                st.session_state.pop("editing_card", None)
                return
            st.markdown(f"### Edit: {existing.name}")
            defaults = existing.to_dict()
            is_new = False
        else:
            st.markdown("### New Agent")
            defaults = {"id": creating.get("id", ""), "name": creating.get("name", ""), "persona": creating.get("persona", ""), "model": "deepseek-v4-pro", "initial_cash": 1_000_000, "max_positions": 4, "max_position_pct": 25.0}
            is_new = True

        agent_id = st.text_input("ID (unique, url-safe)", value=defaults["id"], disabled=not is_new, key="ed_id")
        agent_name = st.text_input("Name", value=defaults["name"], key="ed_name")
        persona = st.text_area("Persona (system prompt)", value=defaults["persona"], height=150, key="ed_persona")

        col1, col2, col3 = st.columns(3)
        available_models = ["deepseek-v4-pro", "deepseek-v4-flash"]
        cur_model = defaults.get("model", "deepseek-v4-pro")
        model_idx = available_models.index(cur_model) if cur_model in available_models else 0
        model = col1.selectbox("Model", available_models, index=model_idx, key="ed_model")
        initial_cash = col2.number_input("Cash", value=defaults.get("initial_cash", 1_000_000), step=100000, format="%d", key="ed_cash")
        max_pos = col3.number_input("Max Positions", value=defaults.get("max_positions", 4), min_value=1, max_value=10, key="ed_pos")

        st.markdown("")
        bc1, bc2 = st.columns([2, 1])
        with bc1:
            if st.button("SAVE", type="primary", use_container_width=True):
                if not agent_id:
                    st.error("ID required.")
                elif not agent_name:
                    st.error("Name required.")
                elif is_new and load_card(agent_id):
                    st.error(f"ID '{agent_id}' already exists.")
                else:
                    card = AgentCard(
                        id=agent_id, name=agent_name, persona=persona,
                        model=model, initial_cash=initial_cash,
                        max_positions=max_pos, max_position_pct=defaults.get("max_position_pct", 25.0),
                    )
                    save_card(card)
                    st.session_state.pop("editing_card", None)
                    st.session_state.pop("creating_new", None)
                    st.toast(f"Saved: {agent_name}")
                    st.rerun()
        with bc2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("editing_card", None)
                st.session_state.pop("creating_new", None)
                st.rerun()


# ═══════════════════════════════════════════════════════════════
# DETAIL
# ═══════════════════════════════════════════════════════════════

def _page_detail():
    import streamlit as st
    import pandas as pd

    st.markdown("# BACKTEST DETAIL")

    selected = st.session_state.get("selected_run")

    if not selected:
        runs = list_results()
        if not runs:
            st.info("No runs yet. Start a backtest from Dashboard.")
            return

        st.markdown("### Select a run")
        for run in runs[:12]:
            status = run.get("status", "done")
            col1, col2, col3 = st.columns([3, 2, 1])
            if status == "done":
                ret = run.get("return", 0)
                col1.markdown(f"**{run.get('date', '?')}** ({run.get('days', '?')}d)")
                col2.markdown(f"Return: **{ret:+.2f}%** | Sharpe: {run.get('sharpe', 0):.2f}")
                if col3.button("View", key=f"pick_{run['file']}"):
                    st.session_state["selected_run"] = run["file"]
                    st.rerun()
            elif status == "running":
                col1.markdown(f"*{run.get('date', '...')}*")
                col2.markdown("Running...")
                col3.button("--", key=f"pick_{run['file']}", disabled=True)
            else:
                col1.markdown(f"~~{run.get('date', '?')}~~")
                col2.markdown("Failed")
                col3.button("--", key=f"pick_{run['file']}", disabled=True)
        return

    data = _load_run(selected)
    if not data:
        st.error(f"Cannot load: {selected}")
        if st.button("Back"):
            st.session_state.pop("selected_run", None)
            st.rerun()
        return

    agent_ids = list(data.get("agent_data", {}).keys())
    if not agent_ids:
        st.error("No agent data found.")
        return

    agent_id = agent_ids[0]
    agent_data = data["agent_data"][agent_id]
    metrics = agent_data.get("metrics", {})

    hc1, hc2 = st.columns([5, 1])
    hc1.caption(f"Agent: {agent_id} | {data.get('start_date','?')} to {data.get('end_date','?')} | {data.get('trading_days',0)} days")
    if hc2.button("Back"):
        st.session_state.pop("selected_run", None)
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["Overview", "Timeline", "Export"])

    with tab1:
        _detail_overview(metrics, agent_data)
    with tab2:
        _detail_timeline(agent_data)
    with tab3:
        _detail_export(data, selected)


def _detail_overview(metrics: dict, agent_data: dict):
    import streamlit as st
    import pandas as pd

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Return", f"{metrics.get('total_return_pct', 0):+.2f}%")
    c2.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
    c3.metric("Max DD", f"-{metrics.get('max_drawdown_pct', 0):.2f}%")
    c4.metric("Win Rate", f"{metrics.get('win_rate', 0):.0f}%")
    c5.metric("Final", f"{metrics.get('final_value', 0):,.0f}")

    curve = agent_data.get("equity_curve", [])
    if curve:
        st.markdown("### Equity Curve")
        from traderharness.ui.components.pixijs_chart import render_equity_curve
        dates_list = [str(d) for d, _ in curve]
        values_list = [float(v) for _, v in curve]
        render_equity_curve(dates_list, values_list, height=240)

    trades = agent_data.get("trades", [])
    if trades:
        st.markdown(f"### Trades ({len(trades)})")
        for t in trades:
            action = t.get("action", "")
            is_buy = action == "buy"
            color = "#ef4444" if is_buy else "#10b981"
            icon = "BUY" if is_buy else "SELL"
            window = t.get("window", "")
            window_label = "开盘" if window == "open" else "尾盘" if window == "close" else ""
            pnl = t.get("pnl")
            pnl_str = f" | PnL: {pnl:+,.0f}" if pnl is not None else ""
            code = t.get("stock_code", "")

            header = (
                f"{t.get('date','')} "
                f"**{icon}** {code} x{t.get('quantity','')} @{t.get('price','')}"
                f" [{window_label}]{pnl_str}"
            )
            with st.expander(header, expanded=False):
                reason = t.get("signal_reasoning", "")
                if reason:
                    st.markdown(reason)
                else:
                    st.caption("No reasoning recorded")

        # Per-stock drill-down with K-line + buy/sell markers
        st.markdown("### Trade Review")
        stock_codes = sorted(set(t.get("stock_code", "") for t in trades if t.get("stock_code")))
        if stock_codes:
            selected_stock = st.selectbox("Select stock", stock_codes, key="review_stock")
            if selected_stock:
                _render_trade_review(selected_stock, trades, agent_data)


def _render_trade_review(stock_code: str, trades: list, agent_data: dict) -> None:
    """Show K-line chart for a stock with buy/sell markers."""
    import streamlit as st
    import pandas as pd
    from pathlib import Path

    dataset_dir = Path.home() / ".finharness" / "dataset"
    daily_path = dataset_dir / "daily.parquet"

    if not daily_path.exists():
        st.warning("Daily K-line data not found.")
        return

    df = pd.read_parquet(daily_path, columns=["stock_code", "date", "open", "high", "low", "close", "volume"])
    stock_df = df[df["stock_code"] == stock_code].copy()
    if stock_df.empty:
        st.warning(f"No K-line data for {stock_code}")
        return

    stock_df["date"] = pd.to_datetime(stock_df["date"])
    stock_df = stock_df.sort_values("date")

    # Filter to backtest period with some padding
    stock_trades = [t for t in trades if t.get("stock_code") == stock_code]
    trade_dates = [pd.Timestamp(t["date"]) for t in stock_trades if t.get("date")]
    if not trade_dates:
        return

    min_date = min(trade_dates) - pd.Timedelta(days=20)
    max_date = max(trade_dates) + pd.Timedelta(days=10)
    stock_df = stock_df[(stock_df["date"] >= min_date) & (stock_df["date"] <= max_date)]

    if stock_df.empty:
        st.warning(f"No K-line data in date range for {stock_code}")
        return

    # Build chart with plotly (A-share: red=up, green=down)
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.75, 0.25], vertical_spacing=0.03,
        )

        # K-line (row 1) — A-share colors: red up, green down
        fig.add_trace(go.Candlestick(
            x=stock_df["date"],
            open=stock_df["open"],
            high=stock_df["high"],
            low=stock_df["low"],
            close=stock_df["close"],
            name=stock_code,
            increasing_line_color="#ef4444",
            increasing_fillcolor="#ef4444",
            decreasing_line_color="#10b981",
            decreasing_fillcolor="#10b981",
        ), row=1, col=1)

        # Buy markers (row 1 only) — below candle low
        buy_trades = [t for t in stock_trades if t.get("action") == "buy"]
        if buy_trades:
            buy_dates = [pd.Timestamp(t["date"]) for t in buy_trades]
            buy_ys = []
            for t in buy_trades:
                td = pd.Timestamp(t["date"])
                row_match = stock_df[stock_df["date"] == td]
                low_val = float(row_match["low"].iloc[0]) if not row_match.empty else float(t.get("price", 0))
                buy_ys.append(low_val * 0.98)

            fig.add_trace(go.Scatter(
                x=buy_dates, y=buy_ys,
                mode="markers+text",
                marker=dict(symbol="triangle-up", size=12, color="#ef4444"),
                text=[f"B x{t.get('quantity','')}" for t in buy_trades],
                textposition="bottom center",
                textfont=dict(size=10, color="#ef4444"),
                name="Buy",
                hovertext=[f"BUY x{t.get('quantity','')} @{t.get('price','')}" for t in buy_trades],
                hoverinfo="text",
            ), row=1, col=1)

        # Sell markers (row 1 only) — above candle high
        sell_trades = [t for t in stock_trades if t.get("action") == "sell"]
        if sell_trades:
            sell_dates = [pd.Timestamp(t["date"]) for t in sell_trades]
            sell_ys = []
            for t in sell_trades:
                td = pd.Timestamp(t["date"])
                row_match = stock_df[stock_df["date"] == td]
                high_val = float(row_match["high"].iloc[0]) if not row_match.empty else float(t.get("price", 0))
                sell_ys.append(high_val * 1.02)

            fig.add_trace(go.Scatter(
                x=sell_dates, y=sell_ys,
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=12, color="#10b981"),
                text=[f"S x{t.get('quantity','')}" for t in sell_trades],
                textposition="top center",
                textfont=dict(size=10, color="#10b981"),
                name="Sell",
                hovertext=[f"SELL x{t.get('quantity','')} @{t.get('price','')}" for t in sell_trades],
                hoverinfo="text",
            ), row=1, col=1)

        # Volume bars (row 2 only)
        vol_colors = ["#ef4444" if c >= o else "#10b981" for c, o in zip(stock_df["close"], stock_df["open"])]
        fig.add_trace(go.Bar(
            x=stock_df["date"], y=stock_df["volume"],
            marker_color=vol_colors, opacity=0.7,
            name="Volume", showlegend=False,
        ), row=2, col=1)

        fig.update_layout(
            height=480,
            margin=dict(l=50, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#1a1a2e",
            font=dict(color="#e0e0e0", family="Courier New", size=11),
            legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center"),
            bargap=0.1,
        )
        # Skip weekends on both axes
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], gridcolor="#2a2a4a", row=1, col=1)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], gridcolor="#2a2a4a", row=2, col=1)
        fig.update_yaxes(gridcolor="#2a2a4a", row=1, col=1)
        fig.update_yaxes(gridcolor="#2a2a4a", row=2, col=1)
        # Disable rangeslider from candlestick
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        st.line_chart(stock_df.set_index("date")["close"], height=200)
        st.caption("Install plotly for candlestick charts: pip install plotly")

    # Trade details for this stock — card style with expandable reasoning
    st.markdown(f"**{stock_code} Trades:**")
    for t in stock_trades:
        action = t.get("action", "")
        is_buy = action == "buy"
        color = "#ef4444" if is_buy else "#10b981"
        icon = "BUY" if is_buy else "SELL"
        window = t.get("window", "")
        window_label = "开盘" if window == "open" else "尾盘" if window == "close" else ""
        pnl = t.get("pnl")
        pnl_str = f" | PnL: {pnl:+,.0f}" if pnl is not None else ""

        header = (
            f"{t.get('date','')} "
            f"**{icon}** {stock_code} x{t.get('quantity','')} @{t.get('price','')}"
            f" [{window_label}]{pnl_str}"
        )
        with st.expander(header, expanded=False):
            reason = t.get("signal_reasoning", "")
            if reason:
                st.markdown(reason)
            else:
                st.caption("No reasoning recorded")


def _detail_timeline(agent_data: dict):
    import streamlit as st

    trajectory = agent_data.get("trajectory")
    if not trajectory:
        st.info("No trajectory data for this run.")
        return

    steps = trajectory.get("steps", [])
    if not steps:
        st.info("Empty trajectory.")
        return

    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for step in steps:
        by_date[step.get("date", "?")].append(step)

    all_dates = sorted(by_date.keys())
    selected_date = st.select_slider("Day", options=all_dates, value=all_dates[-1])

    curve = agent_data.get("equity_curve", [])
    for d, v in curve:
        if str(d) == selected_date:
            st.metric("Portfolio", f"{float(v):,.0f}")
            break

    st.markdown("---")

    day_steps = by_date.get(selected_date, [])
    for i, step in enumerate(day_steps):
        _render_live_step(step, i)


def _detail_export(data: dict, filename: str):
    import streamlit as st

    st.markdown("### Export")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.download_button("Full JSON", json.dumps(data, ensure_ascii=False, default=str, indent=2), file_name=filename, mime="application/json", use_container_width=True)

    with c2:
        agent_data = list(data.get("agent_data", {}).values())[0] if data.get("agent_data") else {}
        traj = agent_data.get("trajectory")
        if traj:
            st.download_button("Trajectory", json.dumps(traj, ensure_ascii=False, default=str, indent=2), file_name=f"traj_{filename}", mime="application/json", use_container_width=True)
        else:
            st.button("Trajectory N/A", disabled=True, use_container_width=True)

    with c3:
        trades = agent_data.get("trades", [])
        if trades:
            import pandas as pd
            st.download_button("Trades CSV", pd.DataFrame(trades).to_csv(index=False), file_name=f"trades_{filename.replace('.json','.csv')}", mime="text/csv", use_container_width=True)
        else:
            st.button("Trades N/A", disabled=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════

def _page_data():
    import streamlit as st

    st.markdown("# DATA")

    dataset = Path.home() / ".finharness" / "dataset"
    files_info = [
        ("daily.parquet", "Daily K-line", True),
        ("5min.parquet", "5-Min Bars", True),
        ("announcements.parquet", "Announcements", False),
        ("news_cls.parquet", "CLS News", False),
        ("dividends.parquet", "Dividends", True),
        ("fundamentals.parquet", "Fundamentals", False),
        ("index_300.parquet", "CSI 300 Index", True),
        ("valuation.parquet", "Valuation", False),
        ("business_segments.parquet", "Business Segments", False),
    ]

    ready = sum(1 for f, _, _ in files_info if (dataset / f).exists())
    total_size = sum((dataset / f).stat().st_size for f, _, _ in files_info if (dataset / f).exists())
    c1, c2 = st.columns(2)
    c1.metric("Ready", f"{ready}/{len(files_info)}")
    c2.metric("Disk", f"{total_size / 1024 / 1024:.0f} MB")

    st.markdown("---")

    for fname, desc, critical in files_info:
        path = dataset / fname
        col1, col2 = st.columns([3, 2])
        col1.markdown(f"**{desc}** `{fname}`")

        if path.exists():
            size = path.stat().st_size / 1024 / 1024
            col2.markdown(f"{_icon('check')} Ready ({size:.1f} MB)", unsafe_allow_html=True)
        else:
            chunk_dirs = {"valuation.parquet": "valuation_chunks", "business_segments.parquet": "business_segments_chunks"}
            cdir = chunk_dirs.get(fname)
            if cdir and (dataset / cdir).exists():
                n = len(list((dataset / cdir).glob("*.parquet")))
                col2.markdown(f"{_icon('clock')} Collecting ({n} chunks)", unsafe_allow_html=True)
            else:
                icon = _icon('x')
                col2.markdown(f"{icon} Missing{'  (critical)' if critical else ''}", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
