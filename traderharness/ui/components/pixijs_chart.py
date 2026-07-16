"""PixiJS-powered equity curve chart embedded in Streamlit via HTML component."""

from __future__ import annotations

import json
from typing import Any

import streamlit.components.v1 as components


def render_equity_curve(dates: list[str], values: list[float], height: int = 240) -> None:
    """Render a pixel-art style equity curve using PixiJS canvas."""
    if not values or len(values) < 2:
        return

    initial = values[0]
    returns = [(v / initial - 1) * 100 for v in values]

    data_json = json.dumps({"dates": dates, "returns": returns, "values": values})

    html = f"""
<div id="chart-container" style="width:100%;height:{height}px;background:#1a1a2e;border:2px solid #533483;position:relative;overflow:hidden;">
  <canvas id="equity-canvas" style="width:100%;height:100%;display:block;"></canvas>
</div>
<script src="https://cdn.jsdelivr.net/npm/pixi.js@8/dist/pixi.min.js"></script>
<script>
(async () => {{
  const container = document.getElementById('chart-container');
  const canvas = document.getElementById('equity-canvas');
  const data = {data_json};
  const returns = data.returns;
  const dates = data.dates;
  const values = data.values;
  const n = returns.length;

  // Sizing
  const W = container.clientWidth;
  const H = {height};
  canvas.width = W * window.devicePixelRatio;
  canvas.height = H * window.devicePixelRatio;
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';

  const app = new PIXI.Application();
  await app.init({{
    canvas: canvas,
    width: W,
    height: H,
    background: 0x1a1a2e,
    antialias: false,
    resolution: window.devicePixelRatio,
    autoDensity: true,
  }});

  const pad = {{ top: 20, right: 20, bottom: 30, left: 50 }};
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;

  const rMin = Math.min(...returns);
  const rMax = Math.max(...returns);
  const range = rMax - rMin || 1;
  const yPad = range * 0.15;
  const yMin = rMin - yPad;
  const yMax = rMax + yPad;

  function xPos(i) {{ return pad.left + (i / (n - 1)) * chartW; }}
  function yPos(r) {{ return pad.top + (1 - (r - yMin) / (yMax - yMin)) * chartH; }}

  // Grid lines
  const grid = new PIXI.Graphics();
  grid.setStrokeStyle({{ width: 1, color: 0x2a2a4e }});

  // Horizontal grid (5 lines)
  for (let i = 0; i <= 4; i++) {{
    const y = pad.top + (i / 4) * chartH;
    grid.moveTo(pad.left, y).lineTo(pad.left + chartW, y).stroke();
  }}

  // Vertical grid
  const step = Math.max(1, Math.floor(n / 6));
  for (let i = 0; i < n; i += step) {{
    const x = xPos(i);
    grid.moveTo(x, pad.top).lineTo(x, pad.top + chartH).stroke();
  }}
  app.stage.addChild(grid);

  // Zero line (dashed effect via short segments)
  if (yMin < 0 && yMax > 0) {{
    const zeroLine = new PIXI.Graphics();
    const zy = yPos(0);
    const dashLen = 6;
    const gapLen = 4;
    zeroLine.setStrokeStyle({{ width: 1, color: 0x533483 }});
    for (let x = pad.left; x < pad.left + chartW; x += dashLen + gapLen) {{
      zeroLine.moveTo(x, zy).lineTo(Math.min(x + dashLen, pad.left + chartW), zy).stroke();
    }}
    app.stage.addChild(zeroLine);
  }}

  // Area fill (gradient via alpha gradient approximation)
  const area = new PIXI.Graphics();
  area.moveTo(xPos(0), yPos(returns[0]));
  for (let i = 1; i < n; i++) {{
    area.lineTo(xPos(i), yPos(returns[i]));
  }}
  area.lineTo(xPos(n - 1), pad.top + chartH);
  area.lineTo(xPos(0), pad.top + chartH);
  area.closePath();
  area.fill({{ color: 0xe94560, alpha: 0.12 }});
  app.stage.addChild(area);

  // Main curve line
  const curve = new PIXI.Graphics();
  curve.setStrokeStyle({{ width: 2, color: 0xe94560 }});
  curve.moveTo(xPos(0), yPos(returns[0]));
  for (let i = 1; i < n; i++) {{
    curve.lineTo(xPos(i), yPos(returns[i]));
  }}
  curve.stroke();
  app.stage.addChild(curve);

  // Data points (small pixel dots)
  const dots = new PIXI.Graphics();
  for (let i = 0; i < n; i++) {{
    dots.rect(xPos(i) - 2, yPos(returns[i]) - 2, 4, 4).fill(0xfeca57);
  }}
  app.stage.addChild(dots);

  // Y-axis labels
  for (let i = 0; i <= 4; i++) {{
    const val = yMax - (i / 4) * (yMax - yMin);
    const label = new PIXI.Text({{
      text: (val >= 0 ? '+' : '') + val.toFixed(2) + '%',
      style: {{ fontFamily: 'VT323, monospace', fontSize: 12, fill: 0x7a7a9e }},
    }});
    label.x = 2;
    label.y = pad.top + (i / 4) * chartH - 7;
    app.stage.addChild(label);
  }}

  // X-axis labels (show a few dates)
  for (let i = 0; i < n; i += step) {{
    const d = dates[i];
    const short = d.slice(5); // MM-DD
    const label = new PIXI.Text({{
      text: short,
      style: {{ fontFamily: 'VT323, monospace', fontSize: 11, fill: 0x7a7a9e }},
    }});
    label.x = xPos(i) - 12;
    label.y = pad.top + chartH + 4;
    app.stage.addChild(label);
  }}

  // Scanline overlay effect
  const scanlines = new PIXI.Graphics();
  for (let y = 0; y < H; y += 4) {{
    scanlines.rect(0, y, W, 1).fill({{ color: 0x000000, alpha: 0.03 }});
  }}
  app.stage.addChild(scanlines);

  // Floating particles (ambient)
  const particles = [];
  for (let i = 0; i < 12; i++) {{
    const p = new PIXI.Graphics();
    p.rect(0, 0, 2, 2).fill({{ color: 0x533483, alpha: 0.4 }});
    p.x = Math.random() * W;
    p.y = Math.random() * H;
    p._vx = (Math.random() - 0.5) * 0.3;
    p._vy = -Math.random() * 0.2 - 0.1;
    app.stage.addChild(p);
    particles.push(p);
  }}

  app.ticker.add((ticker) => {{
    for (const p of particles) {{
      p.x += p._vx * ticker.deltaTime;
      p.y += p._vy * ticker.deltaTime;
      if (p.y < -5) {{ p.y = H + 5; p.x = Math.random() * W; }}
      if (p.x < -5 || p.x > W + 5) {{ p.x = Math.random() * W; }}
    }}
  }});
}})();
</script>
"""
    components.html(html, height=height + 10, scrolling=False)
