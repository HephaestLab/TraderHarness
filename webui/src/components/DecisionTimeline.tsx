import { BrainCircuit, Search, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { formatDate, phaseLabel, toolLabel, windowLabel } from "../locale";
import type { AnalysisDay, AnalyzedAgent, DecisionEvidence, ToolEvidence } from "../types";

function json(value: unknown) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "";
}

function DaySummary({ day }: { day: AnalysisDay }) {
  return (
    <div className="day-summary">
      <span>{day.decision_indices.length} 条决策</span>
      <span>{day.tool_indices.length} 次工具调用</span>
      <span>{day.trades.length} 笔成交</span>
    </div>
  );
}

function DecisionCard({ decision, index }: { decision: DecisionEvidence; index: number }) {
  return (
    <article className="evidence-card decision-evidence">
      <div className="evidence-icon"><BrainCircuit size={15} /></div>
      <div className="evidence-body">
        <header>
          <div>
            <span className="evidence-kind">决策 {String(index + 1).padStart(2, "0")}</span>
            <strong>{phaseLabel(decision.phase)}</strong>
          </div>
          <code>步骤 {decision.step ?? "—"}{decision.sub_window ? ` · ${windowLabel(decision.sub_window)}` : ""}</code>
        </header>
        {decision.reasoning ? (
          <section className="reasoning-block">
            <span>模型推理记录</span>
            <p>{decision.reasoning}</p>
          </section>
        ) : null}
        <section className="response-block">
          <span>智能体回复</span>
          <p>{decision.content || "未记录文本回复。"}</p>
        </section>
        {decision.tool_calls.length ? (
          <details>
            <summary>请求了 {decision.tool_calls.length} 次工具调用</summary>
            <pre>{json(decision.tool_calls)}</pre>
          </details>
        ) : null}
      </div>
    </article>
  );
}

function ToolCard({ tool }: { tool: ToolEvidence }) {
  return (
    <article className="evidence-card tool-evidence">
      <div className="evidence-icon"><Wrench size={14} /></div>
      <div className="evidence-body">
        <header>
          <div><span className="evidence-kind">工具证据</span><strong>{toolLabel(tool.name)}</strong></div>
          <code>步骤 {tool.step ?? "—"}</code>
        </header>
        <details>
          <summary>调用参数</summary>
          <pre>{json(tool.args)}</pre>
        </details>
        <details>
          <summary>完整结果</summary>
          <pre>{json(tool.result)}</pre>
        </details>
      </div>
    </article>
  );
}

export function DecisionTimeline({ agent }: { agent: AnalyzedAgent }) {
  const [date, setDate] = useState(agent.days.at(-1)?.date ?? "");
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState("all");
  const current = agent.days.find((day) => day.date === date) ?? agent.days[0];
  const phases = useMemo(
    () => [...new Set(agent.decisions.map((decision) => decision.phase).filter(Boolean))],
    [agent.decisions],
  );
  if (!current) return <div className="empty-state">本次回测没有记录决策轨迹。</div>;

  const decisions = current.decision_indices
    .map((index) => ({ item: agent.decisions[index], index }))
    .filter(({ item }) => {
      const matchesPhase = phase === "all" || item.phase === phase;
      const corpus = `${item.content} ${item.reasoning}`.toLowerCase();
      return matchesPhase && corpus.includes(query.toLowerCase());
    });
  const tools = current.tool_indices
    .map((index) => agent.tools[index])
    .filter((tool) => `${tool.name} ${json(tool.args)} ${json(tool.result)}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="decision-workbench">
      <aside className="day-rail">
        <span className="rail-label">交易日期</span>
        {agent.days.map((day) => (
          <button key={day.date} className={day.date === current.date ? "active" : ""} onClick={() => setDate(day.date)}>
            <strong>{formatDate(day.date)}</strong>
            <small>{day.decision_indices.length} 条决策 · {day.trades.length} 笔成交</small>
          </button>
        ))}
      </aside>
      <div className="decision-main">
        <div className="evidence-toolbar">
          <div>
            <span className="eyebrow">轨迹证据</span>
            <h2>{formatDate(current.date)}</h2>
            <DaySummary day={current} />
          </div>
          <label className="evidence-search">
            <Search size={14} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索推理内容或工具" />
          </label>
        </div>
        <div className="phase-filter">
          {["all", ...phases].map((value) => (
            <button key={value} className={phase === value ? "active" : ""} onClick={() => setPhase(value)}>
              {phaseLabel(value)}
            </button>
          ))}
        </div>
        {current.brief ? (
          <details className="brief-evidence">
            <summary>发送给智能体的盘前晨报</summary>
            <pre>{current.brief}</pre>
          </details>
        ) : null}
        <div className="evidence-stream">
          {decisions.map(({ item, index }) => <DecisionCard key={`decision-${index}`} decision={item} index={index} />)}
          {tools.map((tool, index) => <ToolCard key={`tool-${tool.step}-${index}`} tool={tool} />)}
          {!decisions.length && !tools.length ? <div className="empty-state">没有符合当前筛选条件的证据。</div> : null}
        </div>
      </div>
    </div>
  );
}
