import { Activity, BrainCircuit, CandlestickChart as ChartIcon, ChevronLeft, ChevronRight, Download, GitCompareArrows, List, Trash2, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { DecisionTimeline } from "../components/DecisionTimeline";
import { DrawdownChart } from "../components/DrawdownChart";
import { EquityChart, type EquityMarker } from "../components/EquityChart";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import { ResultCompare } from "../components/ResultCompare";
import { useToast } from "../components/Toast";
import { TradeReviewWorkbench } from "../components/TradeReviewWorkbench";
import {
  agentDisplayName,
  behaviorLabel,
  benchmarkLabel,
  formatDate,
  sideLabel,
  statusLabel,
  statusTone,
  toolLabel,
  windowLabel,
} from "../locale";
import type { AnalyzedAgent, ResultAnalysis, ResultSummary } from "../types";

function pct(value?: number) {
  return value == null ? "—" : `${value.toFixed(2)}%`;
}

type SortMode = "latest" | "return" | "days";

const MAX_COMPARE = 4;

/** Recency key for result artifacts: YYYYMMDD_HHMMSS prefix, else full filename. */
export function resultArtifactRecencyKey(file: string): string {
  const match = /^(\d{8}_\d{6})/.exec(file);
  return match?.[1] ?? file;
}

function ConfirmDialog({
  file,
  busy,
  onCancel,
  onConfirm,
}: {
  file: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label="删除结果工件"
        onClick={(event) => event.stopPropagation()}
      >
        <h2>删除结果工件？</h2>
        <p>
          将永久删除 <code>{file}</code>，该操作无法恢复。
        </p>
        <div className="dialog-actions">
          <button className="button secondary" onClick={onCancel} disabled={busy}>取消</button>
          <button className="button danger" onClick={onConfirm} disabled={busy}>
            <Trash2 size={15} /> {busy ? "正在删除…" : "确认删除"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Results() {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<ResultSummary[]>([]);
  const [analysis, setAnalysis] = useState<ResultAnalysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortMode>("latest");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compareFiles, setCompareFiles] = useState<string[] | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();
  const file = params.get("file");

  useEffect(() => {
    api.results().then(setItems).catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(() => {
    if (!file) {
      setAnalysis(null);
      return;
    }
    setLoading(true);
    setError("");
    // Only the analysis dossier is loaded up front; the raw artifact can be
    // tens of MB (full trajectory) and is only needed when exporting.
    api.resultAnalysis(file)
      .then(setAnalysis)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [file]);

  const visibleItems = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const filtered = needle
      ? items.filter((item) =>
          [item.file, item.start_date, item.end_date]
            .filter(Boolean)
            .some((text) => String(text).toLowerCase().includes(needle)),
        )
      : [...items];
    if (sort === "return") {
      filtered.sort(
        (a, b) => (b.metrics?.total_return_pct ?? -Infinity) - (a.metrics?.total_return_pct ?? -Infinity),
      );
    } else if (sort === "days") {
      filtered.sort((a, b) => b.trading_days - a.trading_days);
    } else {
      // Newest recorded artifact first — not newest backtest calendar window.
      filtered.sort((a, b) =>
        resultArtifactRecencyKey(b.file).localeCompare(resultArtifactRecencyKey(a.file)),
      );
    }
    return filtered;
  }, [items, filter, sort]);

  function toggleSelect(target: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(target)) {
        next.delete(target);
      } else if (next.size >= MAX_COMPARE) {
        toast.info(`最多同时对比 ${MAX_COMPARE} 个工件`);
      } else {
        next.add(target);
      }
      return next;
    });
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.deleteResult(pendingDelete);
      setItems((current) => current.filter((item) => item.file !== pendingDelete));
      setSelected((current) => {
        const next = new Set(current);
        next.delete(pendingDelete);
        return next;
      });
      toast.success(`已删除结果工件 ${pendingDelete}`);
      setPendingDelete(null);
    } catch (reason) {
      toast.error(`删除失败：${(reason as Error).message}`);
    } finally {
      setDeleting(false);
    }
  }

  const mode: "library" | "detail" | "compare" = compareFiles ? "compare" : file ? "detail" : "library";

  return (
    <section>
      <PageHeader
        eyebrow="研究档案"
        title={mode === "compare" ? "跨回测对比" : mode === "detail" ? "回测研究档案" : "结果资料库"}
        description={
          mode === "compare"
            ? "叠加多个已完成回测的权益曲线，横向对比关键指标。"
            : mode === "detail"
              ? "在同一工件中检查绩效、行为、基准和逐笔交易证据。"
              : "所有本地结果工件均可检查、复盘、对比和导出。"
        }
        actions={
          mode === "detail" && analysis ? (
            <>
              <button className="button secondary" onClick={() => setParams({})}><ChevronLeft size={16} /> 返回资料库</button>
              <a
                className="button secondary"
                href={`/api/results/${encodeURIComponent(file ?? "")}`}
                download={file ?? "result.json"}
                onClick={() => toast.info("已开始导出完整工件")}
              >
                <Download size={16} />
                导出完整工件
              </a>
            </>
          ) : undefined
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      {mode === "compare" ? (
        <ResultCompare files={compareFiles ?? []} onBack={() => setCompareFiles(null)} />
      ) : null}
      {mode === "detail" && loading ? (
        <div role="status" aria-label="正在生成研究档案">
          <div className="metric-grid dossier-metrics" style={{ marginBottom: 16 }}>
            {Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="skeleton skeleton-metric" />
            ))}
          </div>
          <div className="skeleton skeleton-panel" />
        </div>
      ) : null}
      {mode === "detail" && analysis ? (
        <ResultDetail analysis={analysis} />
      ) : null}
      {mode === "library" ? (
        <>
          <div className="library-toolbar">
            <input
              className="filter-input"
              type="search"
              placeholder="按文件名或日期筛选…"
              aria-label="筛选结果工件"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
            <label>
              <span>排序</span>
              <select
                aria-label="结果排序方式"
                value={sort}
                onChange={(event) => setSort(event.target.value as SortMode)}
              >
                <option value="latest">最新优先</option>
                <option value="return">收益率</option>
                <option value="days">交易天数</option>
              </select>
            </label>
          </div>
          {selected.size ? (
            <div className="compare-selection-bar">
              <span>
                已选择 {selected.size} 个工件（最多 {MAX_COMPARE} 个）
                {selected.size < 2 ? "，再选 1 个即可对比" : ""}
              </span>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="button secondary" onClick={() => setSelected(new Set())}>清空选择</button>
                <button
                  className="button primary"
                  disabled={selected.size < 2}
                  onClick={() => setCompareFiles([...selected])}
                >
                  <GitCompareArrows size={15} /> 对比所选 ({selected.size})
                </button>
              </span>
            </div>
          ) : null}
          <div className="result-library">
            {visibleItems.map((item) => {
              const tone = statusTone(item.status);
              return (
                <article
                  className={`result-card${selected.has(item.file) ? " selected" : ""}`}
                  key={item.file}
                  role="button"
                  tabIndex={0}
                  onClick={() => setParams({ file: item.file })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setParams({ file: item.file });
                    }
                  }}
                >
                  <input
                    type="checkbox"
                    className="select-box"
                    aria-label={`选择 ${item.file} 用于对比`}
                    checked={selected.has(item.file)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => toggleSelect(item.file)}
                  />
                  <span className={`result-cell-status result-status status-${tone}`}>
                    <i className={`status-dot ${tone}`} />
                    {statusLabel(item.status)}
                  </span>
                  <strong>{formatDate(item.start_date)} → {formatDate(item.end_date)}</strong>
                  <span className="result-cell-meta">{item.agent_count ?? 1} 个智能体 · {item.trading_days} 个交易日</span>
                  <b className={(item.metrics?.total_return_pct ?? 0) >= 0 ? "positive" : "negative"}>
                    {pct(item.metrics?.total_return_pct)}
                  </b>
                  <span className="result-card-actions">
                    <button
                      className="icon-button"
                      aria-label={`删除结果工件 ${item.file}`}
                      title="删除结果工件"
                      onClick={(event) => {
                        event.stopPropagation();
                        setPendingDelete(item.file);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                    <ChevronRight size={18} />
                  </span>
                </article>
              );
            })}
            {!visibleItems.length ? (
              <div className="empty-state panel">
                {items.length ? "没有匹配筛选条件的结果工件。" : "尚无回测结果工件。"}
              </div>
            ) : null}
          </div>
        </>
      ) : null}
      {pendingDelete ? (
        <ConfirmDialog
          file={pendingDelete}
          busy={deleting}
          onCancel={() => (deleting ? undefined : setPendingDelete(null))}
          onConfirm={confirmDelete}
        />
      ) : null}
    </section>
  );
}

const COMPARISON_PALETTE = ["#48d597", "#5b8def", "#e0a63d", "#e2547a", "#8b6fe0", "#3dc7c0", "#d97757", "#6fd0e8"];

function ComparisonOverview({
  analysis,
  onSelectAgent,
}: {
  analysis: ResultAnalysis;
  onSelectAgent: (agentId: string) => void;
}) {
  const agentIds = Object.keys(analysis.agents);
  const rows = analysis.comparison?.agents ?? agentIds.map((id, index) => ({
    agent_id: id,
    rank: index + 1,
    total_return_pct: analysis.agents[id].metrics.total_return_pct ?? 0,
    annual_return_pct: analysis.agents[id].metrics.annual_return_pct ?? 0,
    sharpe_ratio: analysis.agents[id].metrics.sharpe_ratio ?? 0,
    max_drawdown_pct: analysis.agents[id].metrics.max_drawdown_pct ?? 0,
    win_rate: analysis.agents[id].metrics.win_rate ?? 0,
    final_value: analysis.agents[id].metrics.final_value ?? 0,
    trade_count: analysis.agents[id].trades.length,
  }));
  const benchmarkDaily = analysis.benchmark.daily;
  const benchmarkReturn = benchmarkDaily.length > 1
    ? (benchmarkDaily.at(-1)!.equity / benchmarkDaily[0].equity - 1) * 100
    : null;
  const series = useMemo(() => {
    const values = agentIds.map((id, index) => ({
      label: `${agentDisplayName(id, id)}（${id}）`,
      color: COMPARISON_PALETTE[index % COMPARISON_PALETTE.length],
      values: analysis.agents[id].daily.map((point) => [point.date, point.equity] as [string, number]),
    }));
    if (analysis.benchmark.daily.length) {
      values.push({
        label: benchmarkLabel(analysis.benchmark.name),
        color: "#778191",
        values: analysis.benchmark.daily.map((point) => [point.date, point.equity] as [string, number]),
      });
    }
    return values;
  }, [agentIds, analysis]);

  return (
    <>
      <div className="dossier-toolbar">
        <div className="run-identity">
          <span className="status-chip">{statusLabel(analysis.status)}</span>
          <div><strong>{formatDate(analysis.start_date)} → {formatDate(analysis.end_date)}</strong><small>{analysis.trading_days} 个交易日 · {agentIds.length} 个智能体横向对比</small></div>
        </div>
      </div>
      <article className="panel equity-panel">
        <div className="panel-heading"><div><span className="eyebrow">账户组合证据</span><h2>多智能体权益曲线叠加</h2></div></div>
        <EquityChart series={series} />
      </article>
      <article className="panel comparison-ranking">
        <div className="panel-heading">
          <div><span className="eyebrow">对比总览</span><h2>横向排名</h2></div>
          {analysis.comparison ? (
            <span className="status-chip"><Trophy size={13} /> 最佳：{agentDisplayName(analysis.comparison.best_agent_id, analysis.comparison.best_agent_id)}</span>
          ) : null}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>排名</th><th>智能体</th><th>累计收益</th>
                {benchmarkReturn != null ? <th>相对 {benchmarkLabel(analysis.benchmark.name)}</th> : null}
                <th>夏普比率</th><th>最大回撤</th><th>胜率</th><th>成交次数</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const excess = benchmarkReturn == null ? null : row.total_return_pct - benchmarkReturn;
                return (
                  <tr key={row.agent_id}>
                    <td>#{row.rank}</td>
                    <td><code>{agentDisplayName(row.agent_id, row.agent_id)}（{row.agent_id}）</code></td>
                    <td className={row.total_return_pct >= 0 ? "positive" : "negative"}>{pct(row.total_return_pct)}</td>
                    {excess != null ? (
                      <td className={excess >= 0 ? "positive" : "negative"}>{excess >= 0 ? "+" : ""}{excess.toFixed(2)}%</td>
                    ) : null}
                    <td>{row.sharpe_ratio.toFixed(2)}</td>
                    <td className="negative">{pct(row.max_drawdown_pct)}</td>
                    <td>{pct(row.win_rate)}</td>
                    <td>{row.trade_count}</td>
                    <td><button className="button secondary" onClick={() => onSelectAgent(row.agent_id)}>逐笔复盘 <ChevronRight size={14} /></button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}

function ResultDetail({
  analysis,
}: {
  analysis: ResultAnalysis;
}) {
  const agentIds = Object.keys(analysis.agents);
  const isMultiAgent = agentIds.length > 1;
  const [agentId, setAgentId] = useState<string | null>(isMultiAgent ? null : agentIds[0] ?? null);
  const [tab, setTab] = useState<"review" | "overview" | "decisions" | "trades">("review");

  const activeAgentId = agentId ?? agentIds[0] ?? "";
  const agent = analysis.agents[activeAgentId] ?? analysis.agents[agentIds[0]];
  // Hooks must run unconditionally on every render, so the comparison-overview
  // and missing-agent early returns come after this, not before it.
  const series = useMemo(() => {
    if (!agent) return [];
    const values = [{
      label: `${agentDisplayName(activeAgentId, activeAgentId)}（${activeAgentId}）`,
      color: "#48d597",
      values: agent.daily.map((point) => [point.date, point.equity] as [string, number]),
    }];
    if (analysis.benchmark.daily.length) {
      values.push({
        label: benchmarkLabel(analysis.benchmark.name),
        color: "#778191",
        values: analysis.benchmark.daily.map((point) => [point.date, point.equity] as [string, number]),
      });
    }
    return values;
  }, [agent, activeAgentId, analysis.benchmark]);

  const markers = useMemo<EquityMarker[]>(() => {
    if (!agent) return [];
    return agent.trades.flatMap((trade) => {
      const date = trade.trade_date ?? trade.date;
      if (!date) return [];
      const side = (trade.side ?? trade.action ?? "").toLowerCase();
      return [{ date, side: side === "sell" ? ("sell" as const) : ("buy" as const) }];
    });
  }, [agent]);

  if (isMultiAgent && !agentId) {
    return <ComparisonOverview analysis={analysis} onSelectAgent={setAgentId} />;
  }
  if (!agent) return <div className="empty-state panel">该工件不包含智能体结果。</div>;
  const benchmark = analysis.benchmark.daily;
  const benchmarkReturn = benchmark.length > 1 ? (benchmark.at(-1)!.equity / benchmark[0].equity - 1) * 100 : 0;
  const excessReturn = (agent.metrics.total_return_pct ?? 0) - benchmarkReturn;

  return (
    <>
      <div className="dossier-toolbar">
        <div className="run-identity">
          <span className="status-chip">{statusLabel(analysis.status)}</span>
          <div><strong>{formatDate(analysis.start_date)} → {formatDate(analysis.end_date)}</strong><small>{analysis.trading_days} 个交易日 · 抗污染可回放工件</small></div>
        </div>
        {isMultiAgent ? (
          <>
            <button className="button secondary" onClick={() => setAgentId(null)}><ChevronLeft size={16} /> 返回对比总览</button>
            <label><span>智能体</span><select value={activeAgentId} onChange={(event) => setAgentId(event.target.value)}>{agentIds.map((id) => <option key={id} value={id}>{agentDisplayName(id, id)}（{id}）</option>)}</select></label>
          </>
        ) : <code>{agentDisplayName(activeAgentId, activeAgentId)}（{activeAgentId}）</code>}
      </div>
      <div className="metric-grid dossier-metrics">
        <Metric label="累计收益" value={pct(agent.metrics.total_return_pct)} tone={(agent.metrics.total_return_pct ?? 0) >= 0 ? "positive" : "negative"} />
        <Metric label="夏普比率" value={agent.metrics.sharpe_ratio?.toFixed(2) ?? "—"} note="风险调整后收益" />
        <Metric label="最大回撤" value={pct(agent.metrics.max_drawdown_pct)} tone="negative" />
        <Metric label={`相对 ${benchmarkLabel(analysis.benchmark.name)}`} value={pct(excessReturn)} tone={excessReturn >= 0 ? "positive" : "negative"} />
        <Metric label="胜率" value={pct(agent.metrics.win_rate)} note={`${agent.trades.length} 笔已记录成交`} />
        <Metric label="年化收益" value={pct(agent.metrics.annual_return_pct)} />
      </div>
      <div className="dossier-tabs" role="tablist">
        <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}><ChartIcon size={15} /> 逐笔复盘 <span>{agent.trade_reviews.length}</span></button>
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}><Activity size={15} /> 绩效总览</button>
        <button className={tab === "decisions" ? "active" : ""} onClick={() => setTab("decisions")}><BrainCircuit size={15} /> 完整决策轨迹 <span>{agent.decisions.length}</span></button>
        <button className={tab === "trades" ? "active" : ""} onClick={() => setTab("trades")}><List size={15} /> 成交台账 <span>{agent.trades.length}</span></button>
      </div>
      {tab === "review" ? <TradeReviewWorkbench agent={agent} /> : null}
      {tab === "overview" ? <Overview agent={agent} series={series} markers={markers} /> : null}
      {tab === "decisions" ? <article className="panel decision-panel"><DecisionTimeline agent={agent} /></article> : null}
      {tab === "trades" ? <TradeLedger agent={agent} /> : null}
    </>
  );
}

function Overview({
  agent,
  series,
  markers,
}: {
  agent: AnalyzedAgent;
  series: Parameters<typeof EquityChart>[0]["series"];
  markers: EquityMarker[];
}) {
  return (
    <div className="overview-grid">
      <article className="panel equity-panel">
        <div className="panel-heading"><div><span className="eyebrow">账户组合证据</span><h2>权益曲线与基准对比</h2></div><span className="status-chip">{agent.daily.length} 个观测点</span></div>
        <EquityChart series={series} markers={markers} />
      </article>
      <article className="panel drawdown-panel">
        <div className="panel-heading"><div><span className="eyebrow">下行路径</span><h2>水下回撤曲线</h2></div></div>
        <DrawdownChart points={agent.daily} />
      </article>
      <article className="panel behavior-panel">
        <div className="panel-heading"><div><span className="eyebrow">智能体行为</span><h2>执行行为指纹</h2></div></div>
        <dl>
          {Object.entries(agent.behavior).map(([key, value]) => (
            <div key={key}><dt>{behaviorLabel(key)}</dt><dd>{String(value)}</dd></div>
          ))}
        </dl>
      </article>
      <article className="panel tool-profile">
        <div className="panel-heading"><div><span className="eyebrow">研究过程</span><h2>工具使用情况</h2></div></div>
        <div className="usage-bars">
          {agent.tool_usage.map((item) => {
            const max = agent.tool_usage[0]?.count || 1;
            return <div key={item.name}><span>{toolLabel(item.name)}</span><i><b style={{ width: `${(item.count / max) * 100}%` }} /></i><strong>{item.count}</strong></div>;
          })}
          {!agent.tool_usage.length ? <div className="empty-state">没有记录工具调用。</div> : null}
        </div>
      </article>
      <article className="panel daily-tape">
        <div className="panel-heading"><div><span className="eyebrow">每日记录</span><h2>收益与回撤台账</h2></div></div>
        <div className="daily-grid">{agent.daily.map((point) => <div key={point.date}><span>{formatDate(point.date)}</span><b className={point.daily_return_pct >= 0 ? "positive" : "negative"}>{pct(point.daily_return_pct)}</b><small>回撤 {pct(point.drawdown_pct)}</small></div>)}</div>
      </article>
    </div>
  );
}

function TradeLedger({ agent }: { agent: AnalyzedAgent }) {
  return (
    <article className="panel trade-panel">
      <div className="panel-heading"><div><span className="eyebrow">订单成交</span><h2>含决策理由的逐笔交易台账</h2></div><span className="status-chip">{agent.trades.length} 笔成交</span></div>
      <div className="table-wrap"><table><thead><tr><th>日期 / 窗口</th><th>证券代码</th><th>方向</th><th>数量</th><th>价格</th><th>成交额</th><th>决策理由</th></tr></thead>
        <tbody>{agent.trades.map((trade, index) => {
          const side = trade.side ?? trade.action ?? "—";
          return <tr key={`${trade.trade_date}-${trade.stock_code}-${index}`}><td>{formatDate(trade.trade_date ?? trade.date)}<small>{windowLabel(trade.window)}</small></td><td>{trade.stock_code}</td><td><span className={`side ${side.toLowerCase()}`}>{sideLabel(side)}</span></td><td>{trade.quantity ?? "—"}</td><td>{trade.price == null ? "—" : Number(trade.price).toFixed(2)}</td><td>{trade.amount == null ? "—" : Number(trade.amount).toLocaleString("zh-CN")}</td><td className="rationale-cell">{trade.signal_reasoning ?? trade.reasoning ?? "—"}</td></tr>;
        })}</tbody>
      </table></div>
      {!agent.trades.length ? <div className="empty-state">该智能体在本次回测中没有成交。</div> : null}
    </article>
  );
}
