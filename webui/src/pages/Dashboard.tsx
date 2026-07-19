import { Database, KeyRound, Play, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import { RunForm } from "../components/RunForm";
import { useToast } from "../components/Toast";
import { formatDate, statusTone } from "../locale";
import type { AgentCard, ResultSummary, RuntimeStatus } from "../types";

export function Dashboard() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [error, setError] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    Promise.all([api.status(), api.agents(), api.results()])
      .then(([runtime, cards, runs]) => {
        setStatus(runtime);
        setAgents(cards);
        setResults(runs);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setInitialLoading(false));
  }, []);

  function openRun(id: string) {
    localStorage.setItem("traderharness.activeRun", id);
    navigate(`/live?run=${encodeURIComponent(id)}`);
  }

  async function startDemo() {
    setBusy(true);
    setError("");
    try {
      openRun((await api.startDemo()).id);
    } catch (reason) {
      const message = (reason as Error).message;
      setError(message);
      toast.error(`演示启动失败：${message}`);
      setBusy(false);
    }
  }

  return (
    <section>
      <PageHeader
        eyebrow="运行概览"
        title="智能体研究台"
        description="启动严格遮罩的历史回测，实时观察执行过程，并逐笔复盘每一次决策。"
        actions={
          <button className="button secondary" onClick={startDemo} disabled={busy}>
            <Play size={16} />
            运行免密演示
          </button>
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      {initialLoading && !error ? (
        <div role="status" aria-label="正在加载工作台">
          <div className="metric-grid">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="skeleton skeleton-metric" />
            ))}
          </div>
          <div className="section-grid dashboard-grid">
            <div className="skeleton skeleton-panel" />
            <div className="skeleton skeleton-panel" />
          </div>
        </div>
      ) : null}
      {!initialLoading ? (
        <>
          <div className="metric-grid">
            <Metric
              label="市场数据"
              value={status?.dataset.daily ? "就绪" : "缺失"}
              note={<><Database size={13} /> 全市场本地缓存</>}
              tone={status?.dataset.daily ? "positive" : "negative"}
            />
            <Metric
              label="模型服务"
              value={status?.providers.deepseek_configured ? "已连接" : "仅可回放"}
              note={<><KeyRound size={13} /> 密钥不会离开本机</>}
              tone={status?.providers.deepseek_configured ? "positive" : "warning"}
            />
            <Metric
              label="智能体卡片"
              value={agents.length || "—"}
              note="单执行者与委员会架构"
            />
            <Metric
              label="已完成回测"
              value={results.filter((result) => result.status === "done").length}
              note={<><ShieldCheck size={13} /> 本地结果工件</>}
            />
          </div>
          <div className="section-grid dashboard-grid">
            <article className="panel run-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">新建实验</span>
                  <h2>配置历史回测</h2>
                </div>
                <span className="status-chip">抗数据污染</span>
              </div>
              {agents.length ? (
                <RunForm
                  agents={agents}
                  busy={busy}
                  onSubmit={async (payload) => {
                    setBusy(true);
                    setError("");
                    try {
                      openRun((await api.startRun(payload)).id);
                    } catch (reason) {
                      const message = (reason as Error).message;
                      setError(message);
                      toast.error(`回测启动失败：${message}`);
                      setBusy(false);
                    }
                  }}
                />
              ) : (
                <div className="empty-state">请先创建智能体卡片，再启动回测。</div>
              )}
            </article>
            <aside className="panel recent-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">本地历史</span>
                  <h2>最近回测</h2>
                </div>
              </div>
              <div className="result-list compact">
                {results.slice(0, 8).map((result) => {
                  const tone = statusTone(result.status);
                  return (
                    <button
                      key={result.file}
                      onClick={() => navigate(`/results?file=${encodeURIComponent(result.file)}`)}
                    >
                      <span className={`status-dot ${tone}`} aria-label={result.status} />
                      <span className="result-row-main">
                        <strong>{formatDate(result.start_date)}</strong>
                        <small>{result.agent_count ?? 1} 个智能体 · {result.trading_days} 个交易日</small>
                      </span>
                      <span
                        className={
                          (result.metrics?.total_return_pct ?? 0) >= 0
                            ? "number positive"
                            : "number negative"
                        }
                      >
                        {(result.metrics?.total_return_pct ?? 0).toFixed(2)}%
                      </span>
                    </button>
                  );
                })}
                {!results.length ? <div className="empty-state">尚无回测记录。</div> : null}
              </div>
            </aside>
          </div>
        </>
      ) : null}
    </section>
  );
}
