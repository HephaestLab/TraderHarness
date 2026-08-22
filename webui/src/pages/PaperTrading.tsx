import {
  Activity,
  Ban,
  BellRing,
  Bot,
  BriefcaseBusiness,
  ChevronRight,
  Code2,
  Filter,
  Gauge,
  MessageSquareText,
  Newspaper,
  Play,
  Radio,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, paperEventSocketUrl } from "../api";
import { EquityChart } from "../components/EquityChart";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import { ExpandableText, StructuredPayload } from "../components/StructuredPayload";
import { phaseLabel, sideLabel, statusLabel, toolLabel } from "../locale";
import type { AgentCard, LiveEvent, PaperAgentState, PaperSession } from "../types";

const TERMINAL = new Set(["done", "failed", "cancelled"]);
const SERIES_COLORS = ["#6ee7b7", "#60a5fa", "#f59e0b", "#c084fc", "#fb7185", "#22d3ee"];
type DetailTab = "trades" | "positions" | "trajectory" | "model";
type TraceFilter = "all" | "decision" | "tools" | "orders";

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

function clock(value: unknown) {
  if (!value) return "--:--";
  const parsed = new Date(typeof value === "number" ? value : String(value));
  return Number.isNaN(parsed.getTime())
    ? String(value).slice(11, 16)
    : parsed.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function paperPhaseLabel(value: string) {
  const labels: Record<string, string> = {
    pre_market: "盘前研究",
    open_1: "开盘观察",
    open_2: "开盘决策",
    close_1: "尾盘观察",
    close_2: "尾盘决策",
    collecting: "同步行情",
    complete: "当日完成",
    cancelled: "已停止",
  };
  return labels[value] ?? phaseLabel(value);
}

function normalizedAgents(session: PaperSession | null, cash: number): PaperAgentState[] {
  if (!session) return [];
  if (session.agents?.length) return session.agents;
  return [{
    agent_id: session.agent_id,
    agent_name: session.agent_name,
    status: session.status,
    phase: session.phase,
    account: session.account ?? { cash, equity: cash, return_pct: 0 },
    positions: session.positions ?? [],
    trades: session.trades ?? [],
    equity_curve: session.equity_curve ?? [],
    quote_health: session.quote_health,
    last_event: session.last_event,
    error: session.error,
  }];
}

function eventTitle(event: LiveEvent) {
  if (event.type === "phase_change") return `进入 ${paperPhaseLabel(String(event.data.phase ?? ""))}`;
  if (event.type === "tool_call") return `调用 ${toolLabel(String(event.data.tool ?? event.data.name ?? ""))}`;
  if (event.type === "order_placed") return `提交${sideLabel(String(event.data.side ?? event.data.action ?? ""))}订单`;
  if (event.type === "paper_quote") return "分钟行情完成同步";
  if (event.type === "paper_market_pulse") return "市场异动雷达刷新";
  if (event.type === "paper_news") return "重要快讯进入播报台";
  if (event.type === "paper_clock") return `市场时钟 · ${paperPhaseLabel(String(event.data.phase ?? ""))}`;
  if (event.type === "llm_response") return "模型完成一轮判断";
  if (event.type === "committee_memo") return "研究团队提交备忘录";
  if (event.type === "paper_snapshot") return "账户快照更新";
  if (event.type === "error") return `运行错误 · ${String(event.data.message ?? "")}`;
  return event.type.replaceAll("_", " ");
}

function traceCategory(event: LiveEvent): Exclude<TraceFilter, "all"> | "system" {
  if (["llm_response", "committee_memo"].includes(event.type)) return "decision";
  if (event.type === "tool_call") return "tools";
  if (["order_placed", "order_filled", "conditional_order_event"].includes(event.type)) return "orders";
  return "system";
}

function agentLabel(event: LiveEvent, states: PaperAgentState[]) {
  const id = String(event.data.agent_id ?? "");
  return states.find((item) => item.agent_id === id)?.agent_name
    ?? String(event.data.agent_name || id || "环境");
}

function TraceEventCard({ event, states }: { event: LiveEvent; states: PaperAgentState[] }) {
  const category = traceCategory(event);
  const content = String(event.data.content || event.data.reasoning_content || "");
  return (
    <article className={`trace-card trace-${category}`}>
      <header>
        <span className="trace-sequence">#{event.sequence}</span>
        <strong>{eventTitle(event)}</strong>
        <span className="trace-agent">{agentLabel(event, states)}</span>
        <time>{clock(event.ts ? event.ts * 1000 : event.data.as_of)}</time>
      </header>
      {content ? <ExpandableText text={content} className="trace-narrative" /> : null}
      {event.type === "tool_call" ? (
        <div className="trace-tool-grid">
          <StructuredPayload value={event.data.args ?? {}} title="调用参数" />
          {event.data.result_preview != null ? <StructuredPayload value={event.data.result_preview} title="工具返回" /> : null}
        </div>
      ) : null}
      {event.type === "order_placed" ? <StructuredPayload value={event.data} title="订单详情" /> : null}
      {event.type === "paper_quote" ? (
        <div className="trace-facts">
          <span>源 <b>{String(event.data.source ?? "—")}</b></span>
          <span>新增 <b>{Number(event.data.fetched_rows ?? 0)} 行</b></span>
          <span>缺失 <b>{Number((event.data.missing_codes as unknown[] | undefined)?.length ?? 0)}</b></span>
        </div>
      ) : null}
      {event.type === "paper_snapshot" ? <StructuredPayload value={event.data.account ?? {}} title="账户" /> : null}
      {event.data.error ? <div className="trace-error">{String(event.data.error_code ?? "tool_error")} · {String(event.data.error)}</div> : null}
      {(event.data.content_truncated || event.data.reasoning_truncated) ? <small className="trace-note">界面展示已安全截断，下载“完整轨迹”可审计原文。</small> : null}
    </article>
  );
}

export function PaperTrading() {
  const [params, setParams] = useSearchParams();
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [sessions, setSessions] = useState<PaperSession[]>([]);
  const [session, setSession] = useState<PaperSession | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [activeAgentId, setActiveAgentId] = useState("");
  const [sessionDate, setSessionDate] = useState(nextWeekday());
  const [mode, setMode] = useState<"live" | "accelerated">("live");
  const [initialCash, setInitialCash] = useState(1_000_000);
  const [tab, setTab] = useState<DetailTab>("trajectory");
  const [traceFilter, setTraceFilter] = useState<TraceFilter>("all");
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
        setSelectedAgentIds((current) => current.length ? current : cards.slice(0, Math.min(2, cards.length)).map((item) => item.id));
        setActiveAgentId((current) => current || cards[0]?.id || "");
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
        if (!TERMINAL.has(current.status) && !stopped) pollTimer = window.setTimeout(poll, 2000);
        else {
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
        setEvents((current) => [...current, event].slice(-800));
        if (["paper_snapshot", "paper_quote", "order_placed", "run_end", "error"].includes(event.type)) refreshSession(sessionId).catch((reason: Error) => setError(reason.message));
      };
      socket.onclose = () => {
        setSocketState("offline");
        if (!stopped && !finished) reconnectTimer = window.setTimeout(connect, Math.min(1000 * 2 ** retry++, 8000));
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
    const ids = session.agent_ids?.length ? session.agent_ids : [session.agent_id];
    setSelectedAgentIds(ids);
    setActiveAgentId(ids[0] ?? "");
    setSessionDate(session.session_date);
    setMode(session.mode);
    setInitialCash(session.initial_cash);
  }, [session]);

  function toggleAgent(id: string) {
    setSelectedAgentIds((current) => {
      if (current.includes(id)) return current.length === 1 ? current : current.filter((item) => item !== id);
      return current.length >= 4 ? current : [...current, id];
    });
  }

  async function startPaper() {
    if (!selectedAgentIds.length) return;
    setBusy(true);
    setError("");
    try {
      const started = await api.startPaper({
        agent_ids: selectedAgentIds,
        session_date: sessionDate,
        initial_cash: initialCash,
        mode,
        poll_seconds: 60,
        max_attention_codes: 8,
      });
      localStorage.setItem("traderharness.activePaper", started.id);
      formSyncedSession.current = "";
      setParams({ session: started.id });
      await refreshSessions();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const agentStates = useMemo(() => normalizedAgents(session, initialCash), [session, initialCash]);
  const focused = agentStates.find((item) => item.agent_id === activeAgentId) ?? agentStates[0];
  const allEvents = useMemo(() => {
    const bySequence = new Map<number, LiveEvent>();
    [...(session?.broadcasts ?? []), ...events].forEach((event) => bySequence.set(event.sequence, event));
    return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
  }, [events, session?.broadcasts]);
  const agentEvents = useMemo(() => allEvents.filter((event) => {
    const id = String(event.data.agent_id ?? "");
    return !activeAgentId || !id || id === activeAgentId;
  }), [activeAgentId, allEvents]);
  const visibleTrace = useMemo(() => agentEvents.filter((event) => {
    if (["paper_market_pulse", "paper_news"].includes(event.type)) return false;
    return traceFilter === "all" || traceCategory(event) === traceFilter;
  }), [agentEvents, traceFilter]);
  const modelEvents = useMemo(() => agentEvents.filter((event) => ["llm_response", "committee_memo"].includes(event.type)), [agentEvents]);
  const broadcasts = useMemo(() => allEvents.filter((event) => ["paper_market_pulse", "paper_news"].includes(event.type)).slice().reverse(), [allEvents]);
  const latestPulse = broadcasts.find((event) => event.type === "paper_market_pulse");
  const pulseItems = (latestPulse?.data.items as Array<Record<string, unknown>> | undefined) ?? [];
  const newsItems = broadcasts.flatMap<Record<string, unknown>>((event) => event.type === "paper_news"
    ? ((event.data.items as Array<Record<string, unknown>> | undefined) ?? []).map((item) => ({ ...item, agent_name: event.data.agent_name }))
    : []).slice(0, 16);
  const account = focused?.account ?? session?.account ?? { cash: initialCash, equity: initialCash, return_pct: 0 };
  const requestMetrics = focused?.quote_health?.request_metrics ?? session?.quote_health?.request_metrics ?? {};
  const rateLimited = Number(requestMetrics.rate_limited ?? 0);
  const chartSeries = agentStates.map((state, index) => ({
    label: state.agent_name,
    values: state.equity_curve?.length ? state.equity_curve : [[new Date().toISOString(), state.account.equity]] as Array<[string, number]>,
    color: SERIES_COLORS[index % SERIES_COLORS.length],
  }));
  const rankedAgents = agentStates.slice().sort((a, b) => b.account.return_pct - a.account.return_pct);

  return (
    <section className="paper-page arena-page">
      <PageHeader
        eyebrow="Paper Trading Arena"
        title="多 Agent 每日模拟盘"
        description="同场、同日、同规则对比；重要分钟行情与快讯实时播报，每一次思考、代码和下单都可追溯。"
        actions={session && !TERMINAL.has(session.status) ? <button className="button danger" onClick={() => api.cancelPaper(session.id)}><Ban size={15} /> 安全停止</button> : undefined}
      />
      {error ? <ErrorNotice message={error} /> : null}
      {session?.status === "failed" && session.error ? <ErrorNotice message={session.error} /> : null}

      <div className="arena-launch panel">
        <div className="arena-picker">
          <div className="arena-section-label"><Users size={15} /> 选择参赛 Agent <span>{selectedAgentIds.length}/4</span></div>
          <div className="arena-agent-options">
            {agents.map((agent, index) => {
              const selected = selectedAgentIds.includes(agent.id);
              return <button type="button" key={agent.id} className={selected ? "selected" : ""} onClick={() => toggleAgent(agent.id)} aria-pressed={selected}><i style={{ background: SERIES_COLORS[index % SERIES_COLORS.length] }} /><span><b>{agent.name}</b><small>{agent.model}</small></span><em>{selected ? "已入场" : "加入"}</em></button>;
            })}
          </div>
        </div>
        <div className="arena-launch-controls">
          <label><span>交易日</span><input type="date" value={sessionDate} onChange={(event) => setSessionDate(event.target.value)} /></label>
          <label><span>时钟模式</span><select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="live">实时 1 分钟</option><option value="accelerated">历史加速验收</option></select></label>
          <label><span>每个账户初始资金</span><input type="number" min={10000} step={10000} value={initialCash} onChange={(event) => setInitialCash(Number(event.target.value))} /></label>
          <button className="button primary arena-start" disabled={busy || !selectedAgentIds.length} onClick={startPaper}><Play size={15} /> {busy ? "正在创建…" : `启动 ${selectedAgentIds.length} 个 Agent`}</button>
        </div>
      </div>

      {sessions.length ? (
        <div className="paper-session-strip">
          <span><Radio size={13} /> 历史会话</span>
          <select aria-label="切换模拟盘" value={sessionId} onChange={(event) => setParams({ session: event.target.value })}>
            {!sessionId ? <option value="">选择会话</option> : null}
            {sessions.map((item) => <option key={item.id} value={item.id}>{item.session_date} · {(item.agents?.map((agent) => agent.agent_name).join(" vs ") || item.agent_name)} · {statusLabel(item.status)}</option>)}
          </select>
          <span className={`socket-pill ${socketState}`}><i /> {socketState === "live" ? "事件流已连接" : socketState === "connecting" ? "连接中" : "离线回放"}</span>
        </div>
      ) : null}

      <div className="paper-metric-grid arena-metrics">
        <Metric label="当前查看权益" value={`¥ ${money(account.equity)}`} note={`${focused?.agent_name ?? "等待开赛"} · 现金 ¥ ${money(account.cash)}`} />
        <Metric label="当前收益" value={`${account.return_pct >= 0 ? "+" : ""}${account.return_pct.toFixed(2)}%`} note={`${focused?.trades.length ?? 0} 笔成交`} tone={account.return_pct >= 0 ? "positive" : "warning"} />
        <Metric label="运行阶段" value={focused ? paperPhaseLabel(focused.phase) : "待命"} note={`${session?.clock_state ?? "尚未启动"} · ${agentStates.length || selectedAgentIds.length} Agent`} />
        <Metric label="数据健康" value={focused?.quote_health?.granularity?.toUpperCase() ?? session?.quote_health?.granularity?.toUpperCase() ?? "—"} note={`限流 ${rateLimited} · 缺失 ${focused?.quote_health?.missing_codes?.length ?? 0}`} tone={rateLimited === 0 ? "positive" : "warning"} />
      </div>

      <div className="arena-stage-grid">
        <main className="arena-equity panel">
          <div className="paper-chart-head"><div><span className="eyebrow">Total account value</span><h2>同场净值曲线</h2><p>统一初始资金与撮合规则，点击下方选手聚焦审计。</p></div><div className="paper-live-badge"><Radio size={13} /> {session ? statusLabel(session.status) : "待命"}</div></div>
          <EquityChart height={360} series={chartSeries.length ? chartSeries : [{ label: "等待开赛", values: [[new Date().toISOString(), initialCash]], color: SERIES_COLORS[0] }]} />
          <div className="arena-roster">
            {rankedAgents.length ? rankedAgents.map((state) => {
              const originalIndex = agentStates.findIndex((item) => item.agent_id === state.agent_id);
              return <button key={state.agent_id} className={focused?.agent_id === state.agent_id ? "active" : ""} onClick={() => setActiveAgentId(state.agent_id)}><span className="rank">#{rankedAgents.indexOf(state) + 1}</span><i style={{ background: SERIES_COLORS[originalIndex % SERIES_COLORS.length] }} /><span><b>{state.agent_name}</b><small>{paperPhaseLabel(state.phase)} · {statusLabel(state.status)}</small></span><strong className={state.account.return_pct >= 0 ? "gain" : "loss"}>{state.account.return_pct >= 0 ? "+" : ""}{state.account.return_pct.toFixed(2)}%</strong><ChevronRight size={15} /></button>;
            }) : <div className="arena-waiting"><Sparkles size={18} /><span>选择 Agent 并启动后，这里会形成实时排行榜。</span></div>}
          </div>
        </main>

        <aside className="arena-broadcast panel">
          <header><div><BellRing size={16} /><span><b>市场播报台</b><small>重要快讯 · 分钟异动</small></span></div><em>LIVE</em></header>
          {latestPulse ? <div className="pulse-summary"><span className="up"><TrendingUp size={13} /> 上涨 {Number(latestPulse.data.advancers ?? 0)}</span><span className="down">下跌 {Number(latestPulse.data.decliners ?? 0)}</span><time>{clock(latestPulse.data.as_of)}</time></div> : null}
          <div className="pulse-tape">
            {pulseItems.map((item) => <div key={String(item.stock_code)} className={String(item.importance) === "high" ? "hot" : ""}><span><b>{String(item.stock_name ?? item.stock_code)}</b><small>{String(item.stock_code)}</small></span><strong className={Number(item.change_pct) >= 0 ? "gain" : "loss"}>{Number(item.change_pct) >= 0 ? "+" : ""}{Number(item.change_pct).toFixed(2)}%</strong><em>量比 {Number(item.volume_ratio).toFixed(1)}</em></div>)}
          </div>
          <div className="broadcast-stream">
            {newsItems.length ? newsItems.map((item, index) => <article key={`${String(item.source_id)}-${index}`} className={String(item.importance) === "high" ? "important" : ""}><time>{clock(item.time)}</time><div><span>{String(item.kind) === "announcement" ? "公告" : "快讯"}</span><strong>{String(item.title ?? "市场快讯")}</strong><p>{String(item.content ?? "")}</p><small>{String(item.agent_name ?? "全场")} {item.stock_code ? `· ${String(item.stock_code)}` : ""}</small></div></article>) : <div className="broadcast-empty"><Newspaper size={22} /><b>播报台待命</b><span>开盘后，持仓公告、政策快讯和显著量价异动会自动进入这里。</span></div>}
          </div>
        </aside>
      </div>

      <section className="arena-workbench panel">
        <div className="workbench-head"><div><span className="eyebrow">Agent audit workbench</span><h2>可解释工作轨迹</h2><p>把思考、工具参数、返回值、Python 代码与订单放回一条可读时间线。</p></div><div className="focus-agent"><Bot size={15} /><select aria-label="查看 Agent" value={focused?.agent_id ?? ""} onChange={(event) => setActiveAgentId(event.target.value)}>{agentStates.map((state) => <option key={state.agent_id} value={state.agent_id}>{state.agent_name}</option>)}</select></div></div>
        <div className="paper-tabs" role="tablist">
          <button className={tab === "trajectory" ? "active" : ""} onClick={() => setTab("trajectory")}><Code2 size={14} /> 决策轨迹</button>
          <button className={tab === "trades" ? "active" : ""} onClick={() => setTab("trades")}><Activity size={14} /> 交割 {focused?.trades.length ?? 0}</button>
          <button className={tab === "positions" ? "active" : ""} onClick={() => setTab("positions")}><BriefcaseBusiness size={14} /> 持仓 {focused?.positions.length ?? 0}</button>
          <button className={tab === "model" ? "active" : ""} onClick={() => setTab("model")}><MessageSquareText size={14} /> 模型判断 {modelEvents.length}</button>
        </div>

        {tab === "trajectory" ? (
          <div className="trace-workspace">
            <div className="trace-sidebar">
              <span><Filter size={13} /> 轨迹筛选</span>
              {(["all", "decision", "tools", "orders"] as TraceFilter[]).map((filter) => <button key={filter} className={traceFilter === filter ? "active" : ""} onClick={() => setTraceFilter(filter)}>{filter === "all" ? "全部事件" : filter === "decision" ? "模型判断" : filter === "tools" ? "工具与代码" : "订单执行"}<em>{filter === "all" ? visibleTrace.length : agentEvents.filter((event) => traceCategory(event) === filter).length}</em></button>)}
              <div className="trace-integrity"><ShieldCheck size={16} /><b>审计完整性</b><span>完整原文与环境事件均写入 JSONL，不依赖当前页面缓存。</span></div>
            </div>
            <div className="trace-stream">{visibleTrace.length ? visibleTrace.slice().reverse().map((event) => <TraceEventCard key={event.sequence} event={event} states={agentStates} />) : <div className="paper-empty rich"><Zap size={24} /><b>等待 Agent 开始工作</b><span>阶段切换、工具调用、代码输出、决策和订单会按真实顺序出现。</span></div>}</div>
          </div>
        ) : null}

        {tab === "trades" ? <div className="paper-table-wrap arena-table"><h3>已完成交易 <span>{focused?.trades.length ?? 0}</span></h3>{focused?.trades.length ? <table><thead><tr><th>股票</th><th>方向</th><th>数量</th><th>成交价</th><th>原因</th></tr></thead><tbody>{focused.trades.map((trade, index) => <tr key={index}><td><b>{trade.stock_name ?? trade.stock_code}</b><small>{trade.stock_code}</small></td><td>{sideLabel(trade.action ?? trade.side ?? "")}</td><td>{money(trade.quantity)}</td><td>{money(trade.price)}</td><td className="reason-cell">{trade.reasoning ?? trade.signal_reasoning ?? "—"}</td></tr>)}</tbody></table> : <p className="paper-empty">该 Agent 尚未成交。</p>}</div> : null}
        {tab === "positions" ? <div className="paper-table-wrap arena-table"><h3>当前持仓 <span>{focused?.positions.length ?? 0}</span></h3>{focused?.positions.length ? <table><thead><tr><th>股票</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>浮盈亏</th></tr></thead><tbody>{focused.positions.map((position) => <tr key={position.stock_code}><td><b>{position.stock_code}</b></td><td>{money(position.quantity)}</td><td>{money(position.avg_cost)}</td><td>{money(position.last_price)}</td><td>{money(position.market_value)}</td><td className={(position.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"}>{money(position.unrealized_pnl)}</td></tr>)}</tbody></table> : <p className="paper-empty">当前空仓，等待 Agent 建立观点。</p>}</div> : null}
        {tab === "model" ? <div className="model-decision-grid">{modelEvents.length ? modelEvents.slice().reverse().map((event) => <article key={event.sequence}><header><Bot size={14} /><b>{agentLabel(event, agentStates)}</b><time>{clock(event.ts * 1000)}</time></header><ExpandableText text={String(event.data.content || event.data.reasoning_content || "模型返回已记录")} />{event.data.content_truncated || event.data.reasoning_truncated ? <small>展示已截断，完整轨迹保留原文。</small> : null}</article>) : <p className="paper-empty">模型完成判断后会在这里保留可审计文本。</p>}</div> : null}

        <footer className="paper-health-footer">
          <Gauge size={14} /><span>{focused?.quote_health?.source ?? session?.quote_health?.source ?? "行情源待命"}</span><span>{session?.quote_health?.one_minute_bars ?? 0} 根分钟记录</span>
          {session ? <a href={`/api/paper/sessions/${session.id}/artifacts/events.jsonl`} download>事件审计</a> : null}
          {session ? <a href={`/api/paper/sessions/${session.id}/artifacts/trajectory.jsonl`} download>完整轨迹</a> : null}
          <button title="刷新" onClick={() => sessionId && refreshSession(sessionId)}><RefreshCw size={13} /></button>
        </footer>
      </section>
    </section>
  );
}
