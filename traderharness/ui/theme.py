"""TraderHarness — Pixel Art warm-tone theme (arcade/vaporwave)."""

PIXEL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap');

/* ═══════ TOKENS ═══════ */
:root {
    --bg-deep: #1a1a2e;
    --bg-panel: #16213e;
    --bg-card: #1e2a45;
    --bg-hover: #253352;
    --border-base: #533483;
    --border-glow: #e94560;
    --text-main: #c8c8e0;
    --text-bright: #f0f0ff;
    --text-dim: #7a7a9e;
    --pink: #e94560;
    --cyan: #00d2d3;
    --yellow: #feca57;
    --purple: #533483;
    --green: #10b981;
    --red: #ef4444;
    --font-pixel: 'Press Start 2P', monospace;
    --font-body: 'VT323', monospace;
    --shadow-pixel: 4px 4px 0px #0f3460;
    --shadow-sm: 2px 2px 0px #0f3460;
}

/* ═══════ CRT SCANLINES ═══════ */
[data-testid="stAppViewContainer"]::after {
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    pointer-events: none;
    z-index: 9999;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 3px,
        rgba(0, 0, 0, 0.015) 3px,
        rgba(0, 0, 0, 0.015) 6px
    );
}

/* ═══════ GLOBAL ═══════ */
[data-testid="stAppViewContainer"] {
    background: var(--bg-deep);
    background-image:
        radial-gradient(circle at 15% 50%, rgba(83, 52, 131, 0.06) 0%, transparent 50%),
        radial-gradient(circle at 85% 30%, rgba(233, 69, 96, 0.04) 0%, transparent 50%);
}

[data-testid="stSidebar"] {
    background: var(--bg-panel);
    border-right: 3px solid var(--purple);
}

/* ═══════ TYPOGRAPHY ═══════ */
h1 {
    font-family: var(--font-pixel) !important;
    font-size: 1.2rem !important;
    color: var(--pink) !important;
    text-shadow: 2px 2px 0px var(--purple);
    letter-spacing: -0.5px;
    line-height: 2 !important;
}

h2 {
    font-family: var(--font-pixel) !important;
    font-size: 0.85rem !important;
    color: var(--cyan) !important;
    text-shadow: 1px 1px 0 rgba(0,210,211,0.3);
    line-height: 1.8 !important;
}

h3 {
    font-family: var(--font-pixel) !important;
    font-size: 0.65rem !important;
    color: var(--yellow) !important;
    line-height: 1.8 !important;
}

p, label {
    font-family: var(--font-body) !important;
    color: var(--text-main) !important;
    font-size: 1.2rem !important;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stText"],
[data-testid="stCaptionContainer"] {
    font-family: var(--font-body) !important;
    color: var(--text-main) !important;
    font-size: 1.2rem !important;
}

/* ═══════ METRIC CARDS ═══════ */
[data-testid="stMetric"] {
    background: var(--bg-card);
    border: 2px solid var(--purple);
    border-radius: 0 !important;
    padding: 12px;
    box-shadow: var(--shadow-pixel);
}

[data-testid="stMetric"] [data-testid="stMetricLabel"] {
    color: var(--cyan) !important;
    font-family: var(--font-pixel) !important;
    font-size: 0.45rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--yellow) !important;
    font-family: var(--font-body) !important;
    font-size: 1.8rem !important;
}

/* ═══════ BUTTONS ═══════ */
.stButton > button {
    font-family: var(--font-pixel) !important;
    font-size: 0.55rem !important;
    background: var(--bg-card) !important;
    color: var(--text-main) !important;
    border: 2px solid var(--purple) !important;
    border-radius: 0 !important;
    box-shadow: var(--shadow-sm) !important;
    padding: 10px 16px !important;
    transition: all 0.1s;
    letter-spacing: 0.3px;
}

.stButton > button:hover {
    border-color: var(--cyan) !important;
    color: var(--cyan) !important;
    transform: translate(1px, 1px);
    box-shadow: 2px 2px 0px #0f3460 !important;
}

button[kind="primary"], .stButton > button[kind="primary"] {
    background: var(--pink) !important;
    color: #1a1a2e !important;
    border-color: var(--pink) !important;
    font-weight: bold !important;
}

button[kind="primary"]:hover {
    background: #ff5a75 !important;
    transform: translate(2px, 2px);
    box-shadow: 2px 2px 0px var(--purple) !important;
}

button[kind="primary"]:active {
    transform: translate(4px, 4px);
    box-shadow: 0px 0px 0px var(--purple) !important;
}

/* ═══════ SIDEBAR ═══════ */
[data-testid="stSidebar"] [data-testid="stMarkdown"] h1 {
    font-size: 0.9rem !important;
    color: var(--yellow) !important;
    text-shadow: 2px 2px 0px var(--pink);
}

[data-testid="stSidebar"] label {
    font-family: var(--font-pixel) !important;
    font-size: 0.5rem !important;
    color: var(--text-dim) !important;
}

/* ═══════ INPUTS ═══════ */
input, textarea, select, [data-baseweb="select"] {
    font-family: var(--font-body) !important;
    font-size: 1.2rem !important;
    background: #0f1b33 !important;
    color: var(--cyan) !important;
    border: 2px solid var(--purple) !important;
    border-radius: 0 !important;
}

input:focus, textarea:focus {
    border-color: var(--pink) !important;
}

/* ═══════ TABS ═══════ */
[data-baseweb="tab-list"] { border-bottom: 2px solid var(--purple); }

[data-baseweb="tab"] {
    font-family: var(--font-pixel) !important;
    font-size: 0.5rem !important;
    color: var(--text-dim) !important;
    border-radius: 0 !important;
    padding: 8px 16px !important;
}

[data-baseweb="tab"][aria-selected="true"] {
    color: var(--yellow) !important;
    border-bottom: 3px solid var(--yellow) !important;
}

/* ═══════ DATAFRAMES ═══════ */
[data-testid="stDataFrame"] {
    border: 2px solid var(--purple) !important;
    border-radius: 0 !important;
}

/* ═══════ CHARTS ═══════ */
[data-testid="stVegaLiteChart"], [data-testid="stLineChart"] {
    background: #0f2040 !important;
    border: 2px solid var(--purple);
    border-radius: 0 !important;
    padding: 8px;
    box-shadow: var(--shadow-pixel);
}

/* ═══════ ALERTS ═══════ */
[data-testid="stAlert"] {
    border-radius: 0 !important;
    border: 2px solid;
    font-family: var(--font-body) !important;
    box-shadow: var(--shadow-sm);
}

/* ═══════ EXPANDERS ═══════ */
details {
    border: 2px solid var(--purple) !important;
    border-radius: 0 !important;
    background: var(--bg-card);
}

details:hover { border-color: var(--cyan) !important; }

details summary {
    font-family: var(--font-body) !important;
    font-size: 1.2rem !important;
    color: var(--text-main) !important;
}

[data-testid="stIconMaterial"] {
    display: none !important;
}

/* ═══════ SLIDERS ═══════ */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: var(--pink) !important;
    border-radius: 0 !important;
    width: 14px !important;
    height: 14px !important;
}

/* ═══════ PROGRESS ═══════ */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--pink), var(--yellow)) !important;
    border-radius: 0 !important;
}

/* ═══════ DIVIDER ═══════ */
hr {
    border: none !important;
    border-top: 3px dashed var(--purple) !important;
    margin: 20px 0 !important;
}

/* ═══════ SCROLLBAR ═══════ */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: var(--purple); border-radius: 0; }

/* ═══════ HIDE DEFAULTS ═══════ */
#MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }
</style>
"""


def inject_theme():
    import streamlit as st
    st.markdown(PIXEL_CSS, unsafe_allow_html=True)
