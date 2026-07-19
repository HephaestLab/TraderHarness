import { useId, useMemo, useState } from "react";
import { formatDate } from "../locale";

export interface EquitySeries {
  label: string;
  values: Array<[string, number]>;
  color: string;
}

export interface EquityMarker {
  date: string;
  side: "buy" | "sell";
}

const WIDTH = 1000;
const HEIGHT = 300;
const LEFT = 64;
const RIGHT = 16;
const TOP = 14;
const BOTTOM = 272;

/** 4–5 human-readable ticks covering [min, max]. */
function niceTicks(min: number, max: number): number[] {
  if (!(max > min)) return [min];
  const span = max - min;
  const rough = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const step = (normalized >= 5 ? 10 : normalized >= 2 ? 5 : normalized >= 1 ? 2 : 1) * magnitude;
  const first = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= max + step * 1e-6; value += step) ticks.push(value);
  if (ticks.length >= 3) return ticks;
  return Array.from({ length: 5 }, (_, index) => min + (span * index) / 4);
}

function formatTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`;
  if (abs >= 10_000) return `${(value / 10_000).toFixed(1)}万`;
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function EquityChart({
  series,
  markers,
  height,
}: {
  series: EquitySeries[];
  markers?: EquityMarker[];
  height?: number;
}) {
  const gradientId = useId();
  const [hovered, setHovered] = useState<number | null>(null);
  // A single shared date axis keeps multi-series overlays aligned even when
  // one series (e.g. the benchmark) is missing days the others have.
  const dates = useMemo(
    () => [...new Set(series.flatMap((item) => item.values.map(([date]) => date)))].sort(),
    [series],
  );
  const all = series.flatMap((item) => item.values.map(([, value]) => value));
  if (!all.length) return <div className="chart-empty">暂无权益数据</div>;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const plotWidth = WIDTH - LEFT - RIGHT;
  const x = (date: string) => {
    const index = dateIndex.get(date) ?? 0;
    return dates.length === 1 ? LEFT + plotWidth / 2 : LEFT + (index / (dates.length - 1)) * plotWidth;
  };
  const y = (value: number) => BOTTOM - ((value - min) / range) * (BOTTOM - TOP);
  const ticks = niceTicks(min, max);

  const activeIndex = hovered ?? dates.length - 1;
  const activeDate = dates[activeIndex];
  const readouts = series.map((item) => {
    const match = item.values.find(([date]) => date === activeDate);
    return { label: item.label, color: item.color, value: match?.[1] };
  });

  // Buy/sell markers are anchored to the first (primary) series.
  const primary = series[0];
  const primaryValue = new Map(primary?.values ?? []);
  const plottedMarkers = (markers ?? []).flatMap((marker) => {
    const value = primaryValue.get(marker.date);
    return value == null ? [] : [{ ...marker, px: x(marker.date), py: y(value) }];
  });

  const firstPoints = (primary?.values ?? []).map(
    ([date, value]) => `${x(date).toFixed(1)},${y(value).toFixed(1)}`,
  );
  const areaPath =
    primary && firstPoints.length
      ? `M ${LEFT} ${BOTTOM} L ${firstPoints.join(" L")} L ${x(primary.values.at(-1)![0]).toFixed(1)} ${BOTTOM} Z`
      : null;

  return (
    <div className="equity-chart" style={height ? { height } : undefined}>
      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.label}>
            <i style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <div className="equity-readout" aria-live="polite">
        <span className="readout-date">{formatDate(activeDate)}</span>
        {readouts.map((item) => (
          <span className="readout-item" key={item.label}>
            <i style={{ background: item.color }} />
            <b style={{ color: item.color }}>
              {item.value == null
                ? "—"
                : item.value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}
            </b>
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="账户权益曲线"
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const relative = (event.clientX - rect.left) / rect.width;
          const plotX = relative * WIDTH;
          const ratio = (plotX - LEFT) / plotWidth;
          const index = Math.round(ratio * (dates.length - 1));
          setHovered(Math.max(0, Math.min(dates.length - 1, index)));
        }}
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={primary?.color ?? "#48d597"} stopOpacity=".18" />
            <stop offset="100%" stopColor={primary?.color ?? "#48d597"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((tick) => {
          const gridY = y(tick);
          return (
            <g key={tick}>
              <line x1={LEFT} x2={WIDTH - RIGHT} y1={gridY} y2={gridY} className="chart-grid" />
              <text x={LEFT - 8} y={gridY + 4} textAnchor="end" className="chart-tick">
                {formatTick(tick)}
              </text>
            </g>
          );
        })}
        {areaPath ? <path d={areaPath} fill={`url(#${gradientId})`} /> : null}
        {series.map((item) => (
          <polyline
            key={item.label}
            points={item.values
              .map(([date, value]) => `${x(date).toFixed(1)},${y(value).toFixed(1)}`)
              .join(" ")}
            fill="none"
            stroke={item.color}
            strokeWidth="1.75"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {plottedMarkers.map((marker, index) => (
          <g key={`${marker.date}-${marker.side}-${index}`} className={`trade-marker ${marker.side}`}>
            <path
              d={
                marker.side === "buy"
                  ? `M ${marker.px} ${marker.py + 7} l -6 10 h 12 z`
                  : `M ${marker.px} ${marker.py - 7} l -6 -10 h 12 z`
              }
            />
          </g>
        ))}
        {hovered != null ? (
          <g className="chart-crosshair-group">
            <line
              x1={x(activeDate)}
              x2={x(activeDate)}
              y1={TOP - 6}
              y2={BOTTOM + 8}
              className="chart-crosshair"
            />
            {readouts.map((item) =>
              item.value == null ? null : (
                <circle
                  key={item.label}
                  cx={x(activeDate)}
                  cy={y(item.value)}
                  r="5"
                  fill={item.color}
                  className="crosshair-dot"
                />
              ),
            )}
          </g>
        ) : null}
      </svg>
      <div className="chart-axis">
        <span>{formatDate(dates[0])}</span>
        <span>{dates.length} 个观测点</span>
        <span>{formatDate(dates.at(-1))}</span>
      </div>
    </div>
  );
}
