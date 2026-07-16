"""Pixel Office — embedded React canvas scene for live backtest visualization.

The pixel-office app is built into traderharness/ui/static/pixel-office/.
We serve it via Streamlit's static file serving and communicate via postMessage.
"""

from __future__ import annotations

import streamlit.components.v1 as components

PIXEL_OFFICE_URL = "app/static/pixel-office/index.html?embed"


def render_pet_scene(state: str = "idle", height: int = 380) -> None:
    """Render pixel office scene embedded in an iframe.

    The iframe communicates with the pixel-office app via postMessage.
    States: idle, analyzing, trading, excited, stressed, waiting, sleeping
    """
    state_to_event = {
        "idle": None,
        "analyzing": {"type": "backtest_event", "event": {"type": "phase_change", "ts": 0, "data": {"phase": "pre_market"}}},
        "trading": {"type": "backtest_event", "event": {"type": "tool_call", "ts": 0, "data": {"agent_id": "agent_0", "tool": "place_order", "side": "buy"}}},
        "excited": {"type": "backtest_event", "event": {"type": "tool_call", "ts": 0, "data": {"agent_id": "agent_0", "tool": "place_order", "side": "buy"}}},
        "stressed": {"type": "backtest_event", "event": {"type": "tool_call", "ts": 0, "data": {"agent_id": "agent_0", "tool": "get_kline"}}},
        "waiting": {"type": "backtest_event", "event": {"type": "day_end", "ts": 0, "data": {}}},
        "sleeping": {"type": "backtest_event", "event": {"type": "run_end", "ts": 0, "data": {}}},
    }

    event_msg = state_to_event.get(state)
    post_script = ""
    if event_msg:
        import json
        post_script = f"""
        <script>
        const iframe = document.getElementById('pixel-office-frame');
        iframe.addEventListener('load', () => {{
            setTimeout(() => {{
                iframe.contentWindow.postMessage({json.dumps(event_msg)}, '*');
            }}, 1000);
        }});
        </script>
        """

    html = f"""
    <div style="width:100%;height:{height}px;border:2px solid #3d2f22;border-radius:6px;overflow:hidden;">
        <iframe id="pixel-office-frame"
            src="{PIXEL_OFFICE_URL}"
            style="width:100%;height:100%;border:none;"
            sandbox="allow-scripts allow-same-origin">
        </iframe>
    </div>
    {post_script}
    """
    components.html(html, height=height + 8, scrolling=False)


def render_trader_scene(state: str = "idle", height: int = 380) -> None:
    render_pet_scene(state, height)


def render_trader_animation(state: str = "idle", height: int = 380) -> None:
    render_pet_scene(state, height)
