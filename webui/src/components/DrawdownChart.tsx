import { useState } from "react";
import type { DailyPoint } from "../types";
import { formatDate } from "../locale";

const WIDTH = 1000;
const HEIGHT = 200;
const LEFT = 56;
const RIGHT = 14;
const TOP = 14;
const BOTTOM = 180;

export function DrawdownChart({ points }: { points: DailyPoint[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  if (!points.length) return <div className="chart-empty">暂无回撤数据</div>;
  const worst = Math.min(...points.map((point) => point.drawdown_pct), -0.01);
  const plotWidth = WIDTH - LEFT - RIGHT;
  const x = (index: number) =>
    points.length === 1 ? LEFT + plotWidth / 2 : LEFT + (index / (points.length - 1)) * plotWidth;
  const y = (value: number) => TOP + (value / worst) * (BOTTOM - TOP);

  // Tick labels at 0%, half-worst and worst.
  const ticks = [0, worst / 2, worst];
  const active = hovered ?? points.length - 1;
  const activePoint = points[active];

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${y(point.drawdown_pct).toFixed(1)}`)
    .join(" ");

  return (
    <div className="drawdown-chart">
      <div className="drawdown-readout" aria-live="polite">
        <span>{formatDate(activePoint?.date)}</span>
        <b>{activePoint ? `${activePoint.drawdown_pct.toFixed(2)}%` : "—"}</b>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="账户组合回撤曲线"
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const relative = (event.clientX - rect.left) / rect.width;
          const ratio = (relative * WIDTH - LEFT) / plotWidth;
          const index = Math.round(ratio * (points.length - 1));
          setHovered(Math.max(0, Math.min(points.length - 1, index)));
        }}
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <linearGradient id="drawdown-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff6b72" stopOpacity=".05" />
            <stop offset="100%" stopColor="#ff6b72" stopOpacity=".35" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => {
          const gridY = y(tick);
          return (
            <g key={tick}>
              <line x1={LEFT} x2={WIDTH - RIGHT} y1={gridY} y2={gridY} className="chart-grid" />
              <text x={LEFT - 8} y={gridY + 4} textAnchor="end" className="chart-tick">
                {tick.toFixed(1)}%
              </text>
            </g>
          );
        })}
        <path
          d={`${path} L ${x(points.length - 1).toFixed(1)} ${TOP} L ${x(0).toFixed(1)} ${TOP} Z`}
          fill="url(#drawdown-fill)"
        />
        <path d={path} fill="none" className="drawdown-line" />
        {hovered != null ? (
          <g className="chart-crosshair-group">
            <line
              x1={x(hovered)}
              x2={x(hovered)}
              y1={TOP - 4}
              y2={BOTTOM + 4}
              className="chart-crosshair"
            />
            <circle
              cx={x(hovered)}
              cy={y(activePoint.drawdown_pct)}
              r="5"
              fill="#ff6b72"
              className="crosshair-dot"
            />
          </g>
        ) : null}
      </svg>
      <div className="chart-axis">
        <span>{formatDate(points[0].date)}</span>
        <span>最大回撤 {worst.toFixed(2)}%</span>
        <span>{formatDate(points.at(-1)?.date)}</span>
      </div>
    </div>
  );
}
