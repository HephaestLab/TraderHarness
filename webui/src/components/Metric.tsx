import type { ReactNode } from "react";

interface MetricProps {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warning";
}

export function Metric({ label, value, note, tone = "neutral" }: MetricProps) {
  return (
    <div className={`metric metric-${tone}`}>
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      {note ? <small>{note}</small> : null}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="notice notice-error" role="alert">
      {message}
    </div>
  );
}
