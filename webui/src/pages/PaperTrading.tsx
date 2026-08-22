import {
  Activity,
  Ban,
  Bot,
  Braces,
  BriefcaseBusiness,
  MessageSquareText,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, paperEventSocketUrl } from "../api";
import { EquityChart } from "../components/EquityChart";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import { phaseLabel, sideLabel, statusLabel, toolLabel } from "../locale";
import type { AgentCard, LiveEvent, PaperSession } from "../types";

const TERMINAL = new Set(["done", "failed", "cancelled"]);
type DetailTab = "trades" | "positions" | "trajectory" | "model";

function nextWeekday(): string {
  const value = new Date();
  const day = value.getDay();
  if (day === 6) value.setDate(value.getDate() + 2);
  if (day === 0) value.setDate(value.getDate() + 1);
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

function money(value?: number) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function eventTitle(event: LiveEvent) {
  if (event.type === "phase_change") return `进入 ${phaseLabel(String(event.data.phase ?? ""))}`;
  if (event.type === "tool_call") return `调用 ${toolLabel(String(event.data.tool ?? event.data.name ?? ""))}`;
  if (event.type === "order_placed") return `提交${sideLabel(String(event.data.side ?? event.data.action ?? ""))}订单`;
  if (event.type === "paper_quote") return "一分钟行情快照已同步";
  if (event.type === "paper_clock") return `市场时钟 · ${String(event.data.phase ?? "")}`;
  if (event.type === "llm_response") return "模型完成一轮判断";
  if (event.type === "error") return `运行错误 · ${String(event.data.message ?? "")}`;
  return event.type;
}

function eventDetail(event: LiveEvent) {
  if (event.type === "tool_call") {
    const args = Object.keys(event.data.args ?? {}).length
      ? JSON.stringify(event.data.args)
      : "无参数";
    const failure = event.data.error
      ? ` · ${String(event.data.error_code ?? "tool_error")}: ${String(event.data.error)}`
      : "";
    return `${args}${failure}`;
  }
  if (event.type === "llm_response") {
    return String(event.data.content || event.data.reasoning_content || "模型已返回工具调用");
  }
  if (event.type === "paper_quote") {
    return `${String(event.data.source ?? "行情源")} · ${Number(event.data.fetched_rows ?? 0)} 行 · 缺失 ${Number((event.data.missing_codes as unknown[] | undefined)?.length ?? 0)}`;
  }
  return "";
}

export function PaperTrading() {
  const [params, setParams] = useSearchParams();
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [sessions, setSessions] = useState<PaperSession[]>([]);
  const [session, setSession] = useState<PaperSession | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [sessionDate, setSessionDate] = useState(nextWeekday());
  const [mode, setMode] = useState<"live" | "accelerated">("live");
  const [initialCash, setInitialCash] = useState(1_000_000);
  const [tab, setTab] = useState<DetailTab>("trajectory");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [socketState, setSocketState] = useState("offline");
  const seen = useRef(new Set<number>());
  const formSyncedSession = useRef("");
  const sessionId = params.get("session") ?? localStorage.getItem("traderharness.activePaper") ?? "";

  const refreshSessions = useCallback(async () => {
    const list = await api.paperSessions();
    setSessions(list);
    return list;
  }, []);

  const refreshSession = useCallback(async (id: string) => {
    const current = await api.paperSession(id);
    setSession(current);
    return current;
  }, []);

  useEffect(() => {
    Promise.all([api.agents(), refreshSessions()])
      .then(([cards, list]) => {
        setAgents(cards);
        setAgentId((current) => current || cards[0]?.id || "");
        if (!sessionId && list.length) setParams({ session: list[0].id }, { replace: true });
      })
      .catch((reason: Error) => setError(reason.message));
  }, [refreshSessions, sessionId, setParams]);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      setEvents([]);
      return;
    }
    localStorage.setItem("traderharness.activePaper", sessionId);
    seen.current = new Set();
    setEvents([]);
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let pollTimer: number | undefined;
    let stopped = false;
    let finished = false;
    let retry = 0;

    const poll = async () => {
      try {
        const current = await refreshSession(sessionId);
        if (!TERMINAL.has(current.status) && !stopped) {
          pollTimer = window.setTimeout(poll, 2000);
        } else {
          finished = true;
          refreshSessions().catch(() => undefined);
        }
      } catch (reason) {
        setError((reason as Error).message);
      }
    };
    const connect = () => {
      if (stopped) return;
      setSocketState("connecting");
      socket = new WebSocket(paperEventSocketUrl(sessionId));
      socket.onopen = () => {
        retry = 0;
        setSocketState("live");
      };
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as LiveEvent;
        if (seen.current.has(event.sequence)) return;
        seen.current.add(event.sequence);
        setEvents((current) => [...current, event].slice(-500));
        if (["paper_snapshot", "paper_quote", "order_placed", "run_end", "error"].includes(event.type)) {
          refreshSession(sessionId).catch((reason: Error) => setError(reason.message));
        }
      };
      socket.onclose = () => {
        setSocketState("offline");
        if (!stopped && !finished) {
          reconnectTimer = window.setTimeout(connect, Math.min(1000 * 2 ** retry++, 8000));
        }
      };
    };
    poll();
    connect();
    return () => {
      stopped = true;
      socket?.close();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [refreshSession, refreshSessions, sessionId]);

  useEffect(() => {
    if (!session || formSyncedSession.current === session.id) return;
    formSyncedSession.current = session.id;
    setAgentId(session.agent_id);
    setSessionDate(session.session_date);
    setMode(session.mode);
    setInitialCash(session.initial_cash);
  }, [session]);

  async function startPaper() {
    if (!agentId) return;
    setBusy(true);
    setError("");
    try {
      const started = await api.startPaper({
        agent_id: agentId,
        session_date: sessionDate,
        initial_cash: initialCash,
        mode,
        poll_seconds: 60,
        max_attention_codes: 8,
      });
      localStorage.setItem("traderharness.activePaper", started.id);
      setParams({ session: started.id });
      await refreshSessions();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const modelEvents = useMemo(
    () => events.filter((event) => ["llm_response", "committee_memo"].includes(event.type)),
    [events],
  );
  const account = session?.account ?? { cash: initialCash, equity: initialCash, return_pct: 0 };
  const requestMetrics = session?.quote_health?.request_metrics ?? {};
  const rateLimited = Number(requestMetrics.rate_limited ?? 0);

  return (
    <section className="paper-page">
      <PageHeader
        eyebrow="每日模拟盘"
        title="Agent 实盘演练场"
        description="真实交易规则、环境托管条件单与完整工作轨迹；仅使用虚拟资金，不构成投资建议。"
        actions={
          session && !TERMINAL.has(session.status) ? (
            <button className="button danger" onClick={() => api.cancelPaper(session.id)}>
              <Ban size={15} /> 安全停止
            </button>
          ) : undefined
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      {session?.status === "failed" && session.error ? <ErrorNotice message={session.error} /> : null}

      <div className="paper-launch panel">
        <label>
          <span>执行 Agent</span>
          <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.name} · {agent.model}</option>
            ))}
          </select>
        </label>
        <label>
          <span>交易日</span>
          <input type="date" value={sessionDate} onChange={(event) => setSessionDate(event.target.value)} />
        </label>
        <label>
          <span>时钟模式</span>
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="live">实时 1 分钟</option>
            <option value="accelerated">历史加速验收</option>
          </select>
        </label>
        <label>
          <span>初始资金</span>
          <input
            type="number"
            min={10000}
            step={10000}
            value={initialCash}
            onChange={(event) => setInitialCash(Number(event.target.value))}
          />
        </label>
        <button className="button primary" disabled={busy || !agentId} onClick={startPaper}>
          <Play size={15} /> {busy ? "正在创建…" : "启动每日模拟盘"}
        </button>
      </div>

      {sessions.length ? (
        <div className="paper-session-strip">
          <span>历史会话</span>
          <select
            aria-label="切换模拟盘"
            value={sessionId}
            onChange={(event) => setParams({ session: event.target.value })}
          >
            {!sessionId ? <option value="">选择会话</option> : null}
            {sessions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.session_date} · {item.agent_name} · {statusLabel(item.status)}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="paper-metric-grid">
        <Metric label="账户总权益" value={`¥ ${money(account.equity)}`} note="现金 + 持仓市值" />
        <Metric
          label="累计收益"
          value={`${account.return_pct >= 0 ? "+" : ""}${account.return_pct.toFixed(2)}%`}
          note={`可用现金 ¥ ${money(account.cash)}`}
          tone={account.return_pct >= 0 ? "positive" : "warning"}
        />
        <Metric
          label="市场阶段"
          value={session ? phaseLabel(session.phase) : "待命"}
          note={`${session?.clock_state ?? "尚未启动"} · ${socketState}`}
        />
        <Metric
          label="行情健康"
          value={session?.quote_health?.granularity?.toUpperCase() ?? "—"}
          note={`限流 ${rateLimited} · 缺失 ${session?.quote_health?.missing_codes?.length ?? 0}`}
          tone={rateLimited === 0 ? "positive" : "warning"}
        />
      </div>

      <div className="paper-arena">
        <div className="paper-main panel">
          <div className="paper-chart-head">
            <div>
              <span className="eyebrow">Total account value</span>
              <h2>账户净值与 Agent 行为</h2>
            </div>
            <div className="paper-live-badge">
              <Radio size={13} /> {session ? statusLabel(session.status) : "待命"}
            </div>
          </div>
          <EquityChart
            height={360}
            series={[
              {
                label: session?.agent_name ?? "Paper Agent",
                values: session?.equity_curve?.length
                  ? session.equity_curve
                  : [[new Date().toISOString(), account.equity]],
                color: "#315efb",
              },
            ]}
          />
          <div className="paper-agent-card">
            <span className="paper-agent-icon"><Bot size={20} /></span>
            <div>
              <strong>{session?.agent_name ?? agents.find((agent) => agent.id === agentId)?.name ?? "选择 Agent"}</strong>
              <small>{session?.session_date ?? sessionDate} · {session?.mode === "accelerated" ? "加速验收" : "实时 1 分钟"}</small>
            </div>
            <b className={account.return_pct >= 0 ? "gain" : "loss"}>
              {account.return_pct >= 0 ? "+" : ""}{account.return_pct.toFixed(2)}%
            </b>
          </div>
        </div>

        <aside className="paper-detail panel">
          <div className="paper-tabs" role="tablist">
            <button className={tab === "trades" ? "active" : ""} onClick={() => setTab("trades")}>
              <Activity size={14} /> 交割
            </button>
            <button className={tab === "positions" ? "active" : ""} onClick={() => setTab("positions")}>
              <BriefcaseBusiness size={14} /> 持仓
            </button>
            <button className={tab === "trajectory" ? "active" : ""} onClick={() => setTab("trajectory")}>
              <Braces size={14} /> 轨迹
            </button>
            <button className={tab === "model" ? "active" : ""} onClick={() => setTab("model")}>
              <MessageSquareText size={14} /> 模型
            </button>
          </div>
          <div className="paper-detail-body">
            {tab === "trades" ? (
              <div className="paper-table-wrap">
                <h3>已完成交易 <span>{session?.trades?.length ?? 0}</span></h3>
                {(session?.trades ?? []).length ? (
                  <table><thead><tr><th>股票</th><th>方向</th><th>数量</th><th>成交价</th></tr></thead>
                    <tbody>{session!.trades.map((trade, index) => <tr key={index}>
                      <td>{trade.stock_name ?? trade.stock_code}</td><td>{sideLabel(trade.action ?? trade.side ?? "")}</td>
                      <td>{trade.quantity}</td><td>{money(trade.price)}</td>
                    </tr>)}</tbody></table>
                ) : <p className="paper-empty">Agent 尚未成交。</p>}
              </div>
            ) : null}
            {tab === "positions" ? (
              <div className="paper-table-wrap">
                <h3>当前持仓 <span>{session?.positions?.length ?? 0}</span></h3>
                {(session?.positions ?? []).length ? (
                  <table><thead><tr><th>股票</th><th>数量</th><th>现价</th><th>浮盈亏</th></tr></thead>
                    <tbody>{session!.positions.map((position) => <tr key={position.stock_code}>
                      <td>{position.stock_code}</td><td>{position.quantity}</td><td>{money(position.last_price)}</td>
                      <td className={(position.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"}>{money(position.unrealized_pnl)}</td>
                    </tr>)}</tbody></table>
                ) : <p className="paper-empty">当前空仓，等待 Agent 建立观点。</p>}
              </div>
            ) : null}
            {tab === "trajectory" ? (
              <div className="paper-trajectory">
                <h3>Agent 工作轨迹 <span>{events.length}</span></h3>
                {events.length ? <ol>{events.slice().reverse().map((event) => <li key={event.sequence}>
                  <i className={`paper-event-dot ${event.type}`} />
                  <div><strong>{eventTitle(event)}</strong>{eventDetail(event) ? <p>{eventDetail(event)}</p> : null}<small>#{event.sequence} · {new Date(event.ts * 1000).toLocaleTimeString("zh-CN")}</small></div>
                </li>)}</ol> : <p className="paper-empty">启动后，这里按原始顺序展示阶段、工具、决策、条件单和成交。</p>}
              </div>
            ) : null}
            {tab === "model" ? (
              <div className="paper-model-log">
                <h3>模型判断 <span>{modelEvents.length}</span></h3>
                {modelEvents.length ? modelEvents.slice().reverse().map((event) => <article key={event.sequence}>
                  <header><Bot size={14} /> {session?.agent_name}</header>
                  <p>{String(event.data.content || event.data.reasoning_content || "模型返回已记录")}</p>
                  {event.data.content_truncated || event.data.reasoning_truncated ? <small>界面已截断；“完整轨迹”保留原文。</small> : null}
                </article>) : <p className="paper-empty">模型完成判断后会在这里保留可审计文本。</p>}
              </div>
            ) : null}
          </div>
          <footer className="paper-health-footer">
            <ShieldCheck size={14} />
            <span>{session?.quote_health?.source ?? "行情源待命"}</span>
            <span>{session?.quote_health?.one_minute_bars ?? 0} 根 1 分钟记录</span>
            {session ? <a href={`/api/paper/sessions/${session.id}/artifacts/events.jsonl`} download>事件审计</a> : null}
            {session ? <a href={`/api/paper/sessions/${session.id}/artifacts/trajectory.jsonl`} download>完整轨迹</a> : null}
            <button title="刷新" onClick={() => sessionId && refreshSession(sessionId)}><RefreshCw size={13} /></button>
          </footer>
        </aside>
      </div>
    </section>
  );
}
