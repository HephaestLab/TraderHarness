import { CheckCircle2, ExternalLink, FlaskConical, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import type {
  MaskingShowcase,
  MaskingShowcaseCondition,
  MaskingShowcaseMetrics,
} from "../types";

type ConditionName = "masked" | "unmasked";

function number(value: number | undefined, digits = 2) {
  return value == null ? "—" : value.toFixed(digits);
}

function EquityPreview({ data }: { data: MaskingShowcase }) {
  const curves = [
    { name: "Masked", color: "#48d597", points: data.conditions.masked.equity_curve ?? [] },
    { name: "Unmasked", color: "#f1b65c", points: data.conditions.unmasked.equity_curve ?? [] },
  ];
  const values = curves.flatMap((curve) => curve.points.map((point) => point[1]));
  const min = Math.min(...values, 1_000_000);
  const max = Math.max(...values, 1_000_000);
  const range = max - min || 1;
  const pathFor = (points: Array<[string, number]>) =>
    points
      .map((point, index) => {
        const x = points.length === 1 ? 50 : 4 + (index / (points.length - 1)) * 92;
        const y = 90 - ((point[1] - min) / range) * 76;
        return `${index ? "L" : "M"}${x},${y}`;
      })
      .join(" ");

  return (
    <div className="showcase-chart" aria-label="Equity curve comparison">
      <div className="showcase-legend">
        {curves.map((curve) => (
          <span key={curve.name}><i style={{ background: curve.color }} />{curve.name}</span>
        ))}
      </div>
      {values.length ? (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Recorded equity curves">
          {[20, 50, 80].map((y) => <line key={y} x1="4" x2="96" y1={y} y2={y} />)}
          {curves.map((curve) => (
            <path key={curve.name} d={pathFor(curve.points)} style={{ stroke: curve.color }} />
          ))}
        </svg>
      ) : (
        <div className="showcase-pending">Pilot artifact generation is in progress.</div>
      )}
    </div>
  );
}

function MetricGrid({ metrics }: { metrics: MaskingShowcaseMetrics }) {
  return (
    <div className="metric-grid showcase-metrics">
      <Metric label="Mean return" value={`${number(metrics.total_return_pct, 4)}%`} />
      <Metric label="Alpha vs CSI 300" value={`${number(metrics.alpha_pct, 4)}%`} />
      <Metric label="Sharpe" value={number(metrics.sharpe_ratio, 3)} />
      <Metric label="Max drawdown" value={`${number(metrics.max_drawdown_pct, 4)}%`} />
    </div>
  );
}

function ConditionPanel({ condition }: { condition: MaskingShowcaseCondition }) {
  const passed = condition.audit.status === "pass";
  const pending = condition.audit.status === "pending";
  return (
    <article className="panel showcase-condition">
      <div className="showcase-config">
        <span>Date masking <strong>{condition.mask_dates ? "ON" : "OFF"}</strong></span>
        <span>Entity masking <strong>{condition.mask_entities ? "ON" : "OFF"}</strong></span>
        <span className={passed ? "audit-pass" : pending ? "" : "audit-control"}>
          {passed ? <CheckCircle2 size={15} /> : <ShieldAlert size={15} />}
          {pending
            ? "Leakage audit pending"
            : passed
            ? `Leakage audit passed · ${condition.audit.finding_count} findings`
            : `${condition.audit.finding_count} findings retained for the explicit control`}
        </span>
      </div>
      <MetricGrid metrics={condition.metrics} />
      <div className="showcase-run-table" role="region" aria-label={`${condition.label} recorded runs`}>
        <table>
          <thead><tr><th>Run</th><th>Return</th><th>Alpha</th><th>Trades</th><th>Tokens</th></tr></thead>
          <tbody>
            {condition.runs.map((run) => (
              <tr key={run.id}>
                <td>{run.id}</td>
                <td>{number(run.metrics.total_return_pct, 4)}%</td>
                <td>{number(run.metrics.alpha_pct, 4)}%</td>
                <td>{number(run.metrics.total_trades, 0)}</td>
                <td>{run.llm_total_tokens.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!condition.runs.length ? <p className="showcase-pending">No completed pilot runs yet.</p> : null}
      </div>
    </article>
  );
}

export function Showcase() {
  const [data, setData] = useState<MaskingShowcase | null>(null);
  const [active, setActive] = useState<ConditionName>("masked");
  const [error, setError] = useState("");

  useEffect(() => {
    api.maskingShowcase().then(setData).catch((reason: Error) => setError(reason.message));
  }, []);

  const activeCondition = useMemo(() => data?.conditions[active], [active, data]);

  return (
    <section className="showcase-page">
      <PageHeader
        eyebrow="One-click audited experience"
        title="Masked vs Unmasked"
        description="The same LLM trading agent, market data and execution engine—evaluated with and without visible calendar dates and company identities."
        actions={
          <a className="button secondary" href="https://github.com/HephaestLab/TraderHarness" target="_blank" rel="noreferrer">
            Inspect the code <ExternalLink size={15} />
          </a>
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      {!data && !error ? <div className="skeleton skeleton-panel" role="status" aria-label="Loading experiment" /> : null}
      {data ? (
        <>
          <div className="showcase-banner">
            <FlaskConical size={18} />
            <div><strong>Recorded experiment — not a live backtest</strong><span>{data.summary}</span></div>
            <span className={`status-chip ${data.status === "complete" ? "audit-pass" : ""}`}>{data.status}</span>
          </div>
          <div className="showcase-meta" aria-label="Experiment metadata">
            <span><small>Model</small>{data.model}</span>
            <span><small>Window</small>{data.window.start} → {data.window.end}</span>
            <span><small>Paired repetitions</small>{data.repetitions}</span>
            <span><small>Commit</small>{data.commit?.slice(0, 8) ?? "pending"}</span>
          </div>
          <EquityPreview data={data} />
          <div className="showcase-tabs" role="tablist" aria-label="Experiment condition">
            {(["masked", "unmasked"] as ConditionName[]).map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={active === name}
                className={active === name ? "active" : ""}
                onClick={() => setActive(name)}
              >
                {data.conditions[name].label}
              </button>
            ))}
          </div>
          {activeCondition ? <ConditionPanel condition={activeCondition} /> : null}
          <article className="panel showcase-limitations">
            <span className="eyebrow">Interpretation boundary</span>
            <ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </article>
        </>
      ) : null}
    </section>
  );
}
