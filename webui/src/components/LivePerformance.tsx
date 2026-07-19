import { useMemo, useState } from "react";
import "../live-panel.css";
import { formatDate, statusLabel } from "../locale";
import type { RunContext } from "../liveDerived";

const CHART_HEIGHT = 110;
const PAD_TOP = 10;
const PAD_BOTTOM = 6;

interface LivePerformanceProps {
  context: RunContext;
  /** day_end 事件携带的官方收益率（%），按初始资金计算。 */
  returnsPct: Record<string, number>;
  /** 近窗口事件速率（条/秒）。 */
  eventsPerSecond: number;
}

function formatEquity(value: number) {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

/** 大额净值用"万"缩写，坐标轴更清爽。 */
function formatAxisValue(value: number) {
  if (Math.abs(value) >= 100_000) return `${(value / 10_000).toFixed(1)}万`;
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

const CONTEXT_STATUS_LABELS: Record<RunContext["status"], string> = {
  idle: "待命",
  running: statusLabel("running"),
  done: statusLabel("done"),
  failed: statusLabel("failed"),
  cancelled: statusLabel("cancelled"),
};

export function LivePerformance({
  context,
  returnsPct,
  eventsPerSecond,
}: LivePerformanceProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  const series = useMemo(
    () =>
      context.agents
        .map((agent) => ({ ...agent, points: context.equity[agent.id] ?? [] }))
        .filter((agent) => agent.points.length > 0),
    [context],
  );
  // 共享交易日轴，保证多条曲线横向对齐。
  const dates = useMemo(
    () =>
      [...new Set(series.flatMap((item) => item.points.map(([date]) => date)))].sort(),
    [series],
  );

  const allValues = series.flatMap((item) => item.points.map(([, value]) => value));
  const min = allValues.length ? Math.min(...allValues) : 0;
  const max = allValues.length ? Math.max(...allValues) : 0;
  const span = max - min || Math.abs(max) || 1;
  const paddedMin = min - span * 0.08;
  const paddedMax = max + span * 0.08;

  const x = (index: number) =>
    dates.length <= 1 ? 50 : (index / (dates.length - 1)) * 100;
  const y = (value: number) =>
    PAD_TOP +
    (1 - (value - paddedMin) / (paddedMax - paddedMin)) * (CHART_HEIGHT - PAD_TOP - PAD_BOTTOM);

  const ticks = [paddedMax, (paddedMax + paddedMin) / 2, paddedMin];
  const done = context.dayIndex + 1;
  const progressPct =
    context.totalDays > 0 ? Math.min(100, (done / context.totalDays) * 100) : 0;

  const activeIndex = hovered ?? dates.length - 1;
  const activeDate = dates[activeIndex];

  return (
    <div className="panel lp-panel" aria-label="实时绩效">
      <div className="lp-head">
        <div>
          <span className="eyebrow">实时绩效</span>
          <h2>净值与进度</h2>
        </div>
        <span className={`lp-status-chip ${context.status}`}>
          {CONTEXT_STATUS_LABELS[context.status]}
        </span>
      </div>

      <div className="lp-progress-block">
        <div className="lp-progress-facts">
          <strong>
            {context.totalDays > 0
              ? `第 ${done} / ${context.totalDays} 个交易日`
              : "等待回测启动"}
          </strong>
          {context.date ? <small>当前日期 {formatDate(context.date)}</small> : null}
        </div>
        <div className="lp-progress-track" aria-hidden="true">
          <i style={{ width: `${progressPct}%` }} />
        </div>
        <small className="lp-rate">
          事件速率 {eventsPerSecond.toFixed(1)} 条/秒 · 近 10 秒
        </small>
      </div>

      {context.agents.length ? (
        <div className="lp-agents">
          {context.agents.map((agent) => {
            const points = context.equity[agent.id] ?? [];
            const latest = points.at(-1)?.[1];
            const first = points[0]?.[1];
            const official = returnsPct[agent.id];
            const returnPct =
              official ?? (latest != null && first ? (latest / first - 1) * 100 : null);
            return (
              <div className="lp-agent-row" key={agent.id}>
                <i className="lp-dot" style={{ background: agent.color }} />
                <span className="lp-agent-name" title={agent.name}>
                  {agent.name}
                </span>
                <span className="lp-agent-equity">
                  {latest != null ? formatEquity(latest) : "—"}
                </span>
                <b
                  className={`lp-agent-return ${
                    returnPct == null ? "" : returnPct >= 0 ? "positive" : "negative"
                  }`}
                >
                  {returnPct == null
                    ? "—"
                    : `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%`}
                </b>
              </div>
            );
          })}
        </div>
      ) : null}

      <div
        className="lp-chart-wrap"
        onMouseMove={(event) => {
          if (dates.length < 2) return;
          const rect = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - rect.left) / rect.width;
          const index = Math.round(ratio * (dates.length - 1));
          setHovered(Math.max(0, Math.min(dates.length - 1, index)));
        }}
        onMouseLeave={() => setHovered(null)}
      >
        {series.length ? (
          <>
            <div className="lp-chart-stage">
              <svg
                className="lp-chart"
                viewBox={`0 0 100 ${CHART_HEIGHT}`}
                preserveAspectRatio="none"
                role="img"
                aria-label="各智能体净值曲线"
              >
              {ticks.map((tick) => (
                <line
                  key={tick}
                  className="lp-grid-line"
                  x1="0"
                  x2="100"
                  y1={y(tick)}
                  y2={y(tick)}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {series.map((item) => (
                <polyline
                  key={item.id}
                  className="lp-series-line"
                  points={item.points
                    .map(
                      ([date, value]) =>
                        `${x(dates.indexOf(date)).toFixed(2)},${y(value).toFixed(2)}`,
                    )
                    .join(" ")}
                  stroke={item.color}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {hovered != null && dates.length > 1 ? (
                <line
                  className="lp-crosshair"
                  x1={x(activeIndex)}
                  x2={x(activeIndex)}
                  y1={0}
                  y2={CHART_HEIGHT}
                  vectorEffect="non-scaling-stroke"
                />
              ) : null}
              </svg>
              {ticks.map((tick, index) => (
                <span
                  key={tick}
                  className="lp-axis-label"
                  style={{
                    position: "absolute",
                    left: 4,
                    top: `${(y(tick) / CHART_HEIGHT) * 100}%`,
                    transform: index === ticks.length - 1 ? "translateY(-100%)" : "translateY(2px)",
                  }}
                >
                  {formatAxisValue(tick)}
                </span>
              ))}
              {hovered != null && activeDate ? (
                <div
                  className="lp-tooltip"
                  style={{ left: `clamp(64px, ${x(activeIndex)}%, calc(100% - 64px))`, top: 0 }}
                >
                  <span className="lp-tooltip-date">{formatDate(activeDate)}</span>
                  {series.map((item) => {
                    const point = item.points.find(([date]) => date === activeDate);
                    return (
                      <div className="lp-tooltip-row" key={item.id}>
                        <span>
                          <i style={{ background: item.color }} /> {item.name}
                        </span>
                        <b>{point ? formatEquity(point[1]) : "—"}</b>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
            <div className="lp-chart-axis">
              <span>{formatDate(dates[0])}</span>
              <span>{formatDate(dates.at(-1))}</span>
            </div>
          </>
        ) : (
          <div className="lp-chart-empty">首个交易日结束后展示净值曲线</div>
        )}
      </div>
    </div>
  );
}
