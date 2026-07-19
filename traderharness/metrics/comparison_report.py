"""Self-contained HTML report for multi-agent benchmark runs."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _format(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_comparison_html(
    rows: list[dict[str, Any]],
    behavior: dict[str, dict[str, Any]] | None = None,
    *,
    title: str = "TraderHarness Multi-Agent Comparison",
) -> str:
    behavior = behavior or {}
    columns = list(rows[0]) if rows else ["Rank", "Agent"]
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(_format(row.get(column, '')))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    behavior_cards = "".join(
        (
            f"<article><h3>{escape(agent)}</h3>"
            + "".join(
                f"<div><span>{escape(key.replace('_', ' ').title())}</span>"
                f"<strong>{escape(_format(value))}</strong></div>"
                for key, value in metrics.items()
            )
            + "</article>"
        )
        for agent, metrics in behavior.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{ color-scheme: dark; --ink:#e8edf2; --muted:#8d9aa6; --line:#24313b;
  --panel:#111a21; --accent:#5ce1b9; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#091016; color:var(--ink);
  font:14px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; }}
main {{ width:min(1180px,calc(100% - 40px)); margin:48px auto; }}
.eyebrow {{ color:var(--accent); letter-spacing:.12em; text-transform:uppercase; }}
h1 {{ font:700 clamp(30px,5vw,56px)/1.05 Inter,system-ui,sans-serif; margin:8px 0 28px; }}
h2 {{ margin-top:40px; font:650 22px Inter,system-ui,sans-serif; }}
.table-wrap {{ overflow:auto; border:1px solid var(--line); background:var(--panel); }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:13px 16px; text-align:right; border-bottom:1px solid var(--line); }}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) {{ text-align:left; }}
th {{ color:var(--muted); font-weight:500; white-space:nowrap; }}
tbody tr:first-child {{ background:rgba(92,225,185,.08); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
article {{ padding:18px; background:var(--panel); border:1px solid var(--line); }}
article h3 {{ color:var(--accent); margin:0 0 12px; }}
article div {{ display:flex; justify-content:space-between; gap:16px; padding:6px 0; }}
article span {{ color:var(--muted); }}
</style>
</head>
<body><main>
<div class="eyebrow">Contamination-resistant agent arena</div>
<h1>{escape(title)}</h1>
<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>
<h2>Behavior Diagnostics</h2>
<section class="cards">{behavior_cards or "<p>No behavior records.</p>"}</section>
</main></body></html>"""


def write_comparison_html(
    output: str | Path,
    rows: list[dict[str, Any]],
    behavior: dict[str, dict[str, Any]] | None = None,
    *,
    title: str = "TraderHarness Multi-Agent Comparison",
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_comparison_html(rows, behavior, title=title),
        encoding="utf-8",
    )
    return path
