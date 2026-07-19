import { ChevronRight, GitCompareArrows, LibraryBig } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNotice, PageHeader } from "../components/Metric";
import { RunForm } from "../components/RunForm";
import { useToast } from "../components/Toast";
import type { AgentCard } from "../types";

export function Compare() {
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    api.agents().then(setAgents).catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <section>
      <PageHeader
        eyebrow="独立账户基准实验"
        title="智能体横向对比"
        description="让多个独立智能体在相同市场时钟和初始资金下运行；不共享订单簿，账户互不干扰。"
        actions={<span className="header-badge"><GitCompareArrows size={16} /> 确定性排名</span>}
      />
      {error ? <ErrorNotice message={error} /> : null}
      <article className="panel compare-panel">
        <div className="compare-callout">
          <strong>横向对比不等于多角色委员会。</strong>
          <span>每个入选智能体拥有独立账户；委员会仍是一张智能体卡片，由一个执行者接收只读顾问意见。</span>
        </div>
        {agents.length >= 2 ? (
          <RunForm
            agents={agents}
            multiple
            busy={busy}
            onSubmit={async (payload) => {
              setBusy(true);
              setError("");
              try {
                const run = await api.startRun(payload);
                localStorage.setItem("traderharness.activeRun", run.id);
                navigate(`/live?run=${encodeURIComponent(run.id)}`);
              } catch (reason) {
                const message = (reason as Error).message;
                setError(message);
                toast.error(`对比回测启动失败：${message}`);
                setBusy(false);
              }
            }}
          />
        ) : (
          <div className="empty-state">请至少创建两个智能体卡片后再进行对比。</div>
        )}
      </article>
      <article className="panel compare-guide">
        <div>
          <span className="eyebrow">已完成回测</span>
          <h2>想对比已完成的回测？</h2>
          <p>去结果资料库勾选 2–4 个结果工件，即可叠加权益曲线并横向对比关键指标。</p>
        </div>
        <Link className="button secondary" to="/results">
          <LibraryBig size={16} /> 前往结果资料库 <ChevronRight size={15} />
        </Link>
      </article>
    </section>
  );
}
