import { ChevronLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { EquityChart, type EquitySeries } from "./EquityChart";
import { ErrorNotice } from "./Metric";
import { useToast } from "./Toast";
import { agentDisplayName, formatDate } from "../locale";
import type { ResultAnalysis } from "../types";

export const COMPARE_PALETTE = [
  "#48d597",
  "#5b8def",
  "#e0a63d",
  "#e2547a",
  "#8b6fe0",
  "#3dc7c0",
  "#d97757",
  "#6fd0e8",
];

interface ComparedRun {
  file: string;
  analysis: ResultAnalysis;
  agentId: string;
}

function pct(value?: number) {
  return value == null ? "—" : `${value.toFixed(2)}%`;
}

/**
 * Cross-run comparison: overlays the first agent's equity curve of each
 * selected artifact and contrasts the key metrics side by side.
 */
export function ResultCompare({ files, onBack }: { files: string[]; onBack: () => void }) {
  const [runs, setRuns] = useState<ComparedRun[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all(
      files.map((file) =>
        api.resultAnalysis(file).then((analysis) => {
          const agentId = Object.keys(analysis.agents)[0] ?? "";
          return { file, analysis, agentId };
        }),
      ),
    )
      .then(setRuns)
      .catch((reason: Error) => {
        setError(reason.message);
        toast.error(`加载对比数据失败：${reason.message}`);
      })
      .finally(() => setLoading(false));
  }, [files, toast]);

  const series = useMemo<EquitySeries[]>(
    () =>
      runs.map((run, index) => ({
        label: `${formatDate(run.analysis.start_date)} · ${agentDisplayName(run.agentId, run.agentId)}`,
        color: COMPARE_PALETTE[index % COMPARE_PALETTE.length],
        values: (run.analysis.agents[run.agentId]?.daily ?? []).map(
          (point) => [point.date, point.equity] as [string, number],
        ),
      })),
    [runs],
  );

  return (
    <>
      <div className="dossier-toolbar">
        <div className="run-identity">
          <span className="status-chip">跨回测对比</span>
          <div>
            <strong>{runs.length || files.length} 个结果工件</strong>
            <small>每个工件取第一个智能体的权益曲线叠加</small>
          </div>
        </div>
        <button className="button secondary" onClick={onBack}>
          <ChevronLeft size={16} /> 返回资料库
        </button>
      </div>
      {error ? <ErrorNotice message={error} /> : null}
      {loading ? (
        <>
          <div className="skeleton skeleton-panel" style={{ marginBottom: 16 }} aria-label="正在加载对比图表" />
          <div className="skeleton skeleton-panel" aria-label="正在加载对比指标" />
        </>
      ) : null}
      {!loading && runs.length ? (
        <>
          <article className="panel equity-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">账户组合证据</span>
                <h2>跨回测权益曲线叠加</h2>
              </div>
            </div>
            <EquityChart series={series} />
          </article>
          <article className="panel comparison-ranking">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">对比总览</span>
                <h2>关键指标对比</h2>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>回测区间</th>
                    <th>智能体</th>
                    <th>累计收益</th>
                    <th>夏普比率</th>
                    <th>最大回撤</th>
                    <th>胜率</th>
                    <th>成交次数</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run, index) => {
                    const agent = run.analysis.agents[run.agentId];
                    const totalReturn = agent?.metrics.total_return_pct;
                    return (
                      <tr key={run.file}>
                        <td>
                          <span className="readout-item">
                            <i
                              style={{
                                background: COMPARE_PALETTE[index % COMPARE_PALETTE.length],
                                borderRadius: "50%",
                                display: "inline-block",
                                height: 7,
                                marginRight: 6,
                                width: 7,
                              }}
                            />
                            {formatDate(run.analysis.start_date)} → {formatDate(run.analysis.end_date)}
                          </span>
                        </td>
                        <td>
                          <code>{agentDisplayName(run.agentId, run.agentId)}（{run.agentId}）</code>
                        </td>
                        <td className={(totalReturn ?? 0) >= 0 ? "positive" : "negative"}>
                          {pct(totalReturn)}
                        </td>
                        <td>{agent?.metrics.sharpe_ratio?.toFixed(2) ?? "—"}</td>
                        <td className="negative">{pct(agent?.metrics.max_drawdown_pct)}</td>
                        <td>{pct(agent?.metrics.win_rate)}</td>
                        <td>{agent?.trades.length ?? 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>
        </>
      ) : null}
      {!loading && !runs.length && !error ? (
        <div className="empty-state panel">所选工件均无法用于对比。</div>
      ) : null}
    </>
  );
}
