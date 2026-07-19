import { Ban, FolderOpen, Pause, Play, Plus, Radio } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, eventSocketUrl } from "../api";
import { ErrorNotice, Metric, PageHeader } from "../components/Metric";
import { LivePerformance } from "../components/LivePerformance";
import { OfficeFloor } from "../components/OfficeFloor";
import {
  EVENT_GROUP_LABELS,
  buildRunContext,
  eventAgentId,
  eventRate,
  filterEvents,
  type EventGroup,
} from "../liveDerived";
import {
  agentDisplayName,
  eventTypeLabel,
  phaseLabel,
  sideLabel,
  statusLabel,
  toolLabel,
} from "../locale";
import type { AgentCard, LiveEvent, RunState } from "../types";

const TERMINAL = new Set(["done", "failed", "cancelled"]);
// Month-long multi-agent runs emit tens of thousands of events; the page
// keeps a bounded window (dedup + totals tracked separately) so memory and
// re-render cost stay flat no matter how long the run goes.
const MAX_BUFFERED_EVENTS = 400;
const MAX_RENDERED_EVENTS = 80;
// 进度 / 净值曲线依赖的里程碑事件量很小（每交易日两条），单独累积，
// 不被上面的滚动缓冲淘汰，保证长时间运行的曲线完整。
const MILESTONE_TYPES = new Set(["run_start", "day_start", "day_end", "run_end"]);
const RATE_WINDOW_MS = 10_000;
const GROUP_ORDER: EventGroup[] = ["all", "phase", "tool", "order", "error", "think"];

interface EquitySnapshot {
  equity: number;
  return_pct: number;
}

function eventLabel(event: LiveEvent) {
  if (event.type === "phase_change") return `阶段 · ${phaseLabel(String(event.data.phase ?? ""))}`;
  if (event.type === "tool_call") return `工具 · ${toolLabel(String(event.data.tool ?? ""))}`;
  if (event.type === "order_placed") return `订单 · ${sideLabel(String(event.data.side ?? ""))}`;
  if (event.type === "run_error") return `错误 · ${String(event.data.error ?? "")}`;
  return eventTypeLabel(event.type);
}

export function LiveRun() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunState | null>(null);
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [milestones, setMilestones] = useState<LiveEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);
  const [returnsPct, setReturnsPct] = useState<Record<string, number>>({});
  const [groupFilter, setGroupFilter] = useState<EventGroup>("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [paused, setPaused] = useState(false);
  // 暂停滚动时冻结渲染快照；新事件继续在 events 里累积。
  const [snapshot, setSnapshot] = useState<LiveEvent[]>([]);
  const [error, setError] = useState("");
  const [socketState, setSocketState] = useState("offline");
  const [runList, setRunList] = useState<RunState[]>([]);
  const [listLoaded, setListLoaded] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const retry = useRef(0);
  const seen = useRef<Set<number>>(new Set());
  const paramRunId = params.get("run");
  const runId = paramRunId
    ?? localStorage.getItem("traderharness.activeRun")
    ?? "";

  const refreshRuns = useCallback(() => {
    api
      .runs()
      .then((list) => {
        setRunList(list);
        setListLoaded(true);
      })
      .catch((reason: Error) => {
        setListLoaded(true);
        setError(reason.message);
      });
  }, []);

  useEffect(() => {
    api.agents().then(setAgents).catch((reason: Error) => setError(reason.message));
    refreshRuns();
  }, [refreshRuns]);

  // 没有指定运行时，自动打开最近的一个（优先仍在运行中的）。
  useEffect(() => {
    if (runId || !listLoaded) return;
    const preferred = runList.find((item) => !TERMINAL.has(item.status)) ?? runList[0];
    if (preferred) setParams({ run: preferred.id }, { replace: true });
  }, [runId, listLoaded, runList, setParams]);

  // 运行到达终态后刷新列表，让切换器里的状态保持最新。
  useEffect(() => {
    if (run && TERMINAL.has(run.status)) refreshRuns();
  }, [run, refreshRuns]);

  useEffect(() => {
    if (!runId) return;
    localStorage.setItem("traderharness.activeRun", runId);
    seen.current = new Set();
    setEvents([]);
    setMilestones([]);
    setEventCount(0);
    setReturnsPct({});
    setGroupFilter("all");
    setAgentFilter("all");
    setPaused(false);
    setSnapshot([]);
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let pollTimer: number | undefined;
    let stopped = false;
    let finished = false;
    const load = () =>
      api.run(runId).then(setRun).catch((reason: Error) => {
        // URL 未指定运行时，本地记忆的运行 ID 可能已随服务重启失效：
        // 清除记忆并回退到"自动选择最近运行"，而不是困在报错页。
        if (!paramRunId) {
          localStorage.removeItem("traderharness.activeRun");
          refreshRuns();
          return;
        }
        setError(reason.message);
      });
    // The run_end event races the manager persisting the result artifact, so
    // a single status fetch can still observe "running"; poll briefly until
    // the run reaches a terminal state.
    const pollUntilTerminal = (attempt = 0) => {
      api.run(runId)
        .then((state) => {
          setRun(state);
          if (!stopped && !TERMINAL.has(state.status) && attempt < 30) {
            pollTimer = window.setTimeout(() => pollUntilTerminal(attempt + 1), 1000);
          }
        })
        .catch((reason: Error) => setError(reason.message));
    };
    const accept = (incoming: LiveEvent) => {
      if (seen.current.has(incoming.sequence)) return;
      seen.current.add(incoming.sequence);
      setEventCount((count) => count + 1);
      setEvents((current) => {
        const next = [...current, incoming];
        return next.length > MAX_BUFFERED_EVENTS
          ? next.slice(next.length - MAX_BUFFERED_EVENTS)
          : next;
      });
      if (MILESTONE_TYPES.has(incoming.type)) {
        setMilestones((current) => [...current, incoming]);
      }
      if (incoming.type === "day_end" && incoming.data.equity) {
        const snapshots = incoming.data.equity as Record<string, EquitySnapshot>;
        setReturnsPct((current) => {
          const next = { ...current };
          for (const [id, snapshot] of Object.entries(snapshots)) {
            if (typeof snapshot?.return_pct === "number") next[id] = snapshot.return_pct;
          }
          return next;
        });
      }
      if (["run_end", "run_error", "error"].includes(incoming.type)) {
        finished = true;
        pollUntilTerminal();
      }
    };
    const connect = () => {
      if (stopped) return;
      setSocketState("connecting");
      socket = new WebSocket(eventSocketUrl(runId));
      socket.onopen = () => {
        retry.current = 0;
        setSocketState("live");
      };
      socket.onmessage = (message) => {
        accept(JSON.parse(message.data) as LiveEvent);
      };
      socket.onclose = () => {
        setSocketState("offline");
        // Once the run has ended the server closes the stream for good;
        // reconnecting would only replay the same events forever.
        if (!stopped && !finished) {
          const delay = Math.min(1000 * 2 ** retry.current++, 8000);
          timer = window.setTimeout(connect, delay);
        }
      };
    };
    load();
    connect();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      if (pollTimer) window.clearTimeout(pollTimer);
      socket?.close();
    };
  }, [runId, paramRunId, refreshRuns]);

  // 未暂停时渲染快照跟随最新事件流；暂停期间保持冻结。
  useEffect(() => {
    if (!paused) setSnapshot(events);
  }, [events, paused]);

  const visibleAgents = useMemo(() => {
    const ids = run?.agents ?? [];
    const matches = agents.filter((agent) => ids.includes(agent.id));
    return matches.length
      ? matches.map(({ id, name }) => ({ id, name: agentDisplayName(id, name) }))
      : ids.map((id) => ({ id, name: agentDisplayName(id, id) }));
  }, [agents, run]);
  const agentNames = useMemo(
    () => new Map(visibleAgents.map((agent) => [agent.id, agent.name])),
    [visibleAgents],
  );

  const runContext = useMemo(
    () => buildRunContext(milestones, visibleAgents, run?.status),
    [milestones, visibleAgents, run?.status],
  );
  const eventsPerSecond = useMemo(() => eventRate(events, RATE_WINDOW_MS), [events]);

  const filter = useMemo(
    () => ({ types: groupFilter, agentId: agentFilter }),
    [groupFilter, agentFilter],
  );
  const filteredLatest = useMemo(() => filterEvents(events, filter), [events, filter]);
  const filteredSnapshot = useMemo(
    () => filterEvents(snapshot, filter),
    [snapshot, filter],
  );
  const pendingCount = paused ? filteredLatest.length - filteredSnapshot.length : 0;
  const visibleEvents = useMemo(
    () => filteredSnapshot.slice(-MAX_RENDERED_EVENTS).reverse(),
    [filteredSnapshot],
  );

  const latest = events.at(-1);
  const status = run?.status ?? "loading";

  async function startDemo() {
    setDemoBusy(true);
    setError("");
    try {
      const started = await api.startDemo();
      localStorage.setItem("traderharness.activeRun", started.id);
      setParams({ run: started.id });
    } catch (reason) {
      setError((reason as Error).message);
      setDemoBusy(false);
    }
  }

  // 没有选中任何运行时，也直接把办公室摆出来（全体智能体工位待命），
  // 并提供演示 / 新建入口，不再要求手输运行 ID。
  if (!runId) {
    const idleAgents = agents.map((agent) => ({
      id: agent.id,
      name: agentDisplayName(agent.id, agent.name),
    }));
    const idleContext = buildRunContext([], idleAgents, "idle");
    return (
      <section>
        <PageHeader
          eyebrow="实时运行"
          title="量化研究大厅"
          description="办公室已就绪。启动一次回测，这里会实时直播智能体的每一步决策。"
        />
        {error ? <ErrorNotice message={error} /> : null}
        <div className="live-layout-v2">
          <OfficeFloor agents={idleAgents} runContext={idleContext} />
          <div className="lp-rail">
            <aside className="panel lp-idle-panel" aria-label="启动回测">
              <span className="eyebrow">待命</span>
              <h2>{listLoaded ? "暂无运行记录" : "正在查询运行记录…"}</h2>
              <p>
                办公室里的智能体已经在工位上待命。从免密演示快速体验，
                或去工作台配置一次真实回测。
              </p>
              <div className="lp-idle-actions">
                <button className="button primary" disabled={demoBusy} onClick={startDemo}>
                  <Play size={15} />
                  {demoBusy ? "正在启动…" : "运行免密演示"}
                </button>
                <button className="button secondary" onClick={() => navigate("/")}>
                  <Plus size={15} />
                  新建回测
                </button>
              </div>
            </aside>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section>
      <PageHeader
        eyebrow="实时运行"
        title="回测控制室"
        description={`运行 ${runId.slice(0, 12)} · 带日志的 WebSocket 事件流`}
        actions={
          <>
            {runList.length ? (
              <select
                className="lp-select lp-run-switcher"
                aria-label="切换运行"
                value={runId}
                onChange={(event) => {
                  localStorage.setItem("traderharness.activeRun", event.target.value);
                  setParams({ run: event.target.value });
                }}
              >
                {runList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id.slice(0, 8)} · {statusLabel(item.status)} ·{" "}
                    {item.agents?.length ?? 0} 个智能体
                  </option>
                ))}
              </select>
            ) : null}
            {run && !TERMINAL.has(run.status) ? (
              <button
                className="button danger"
                onClick={() => api.cancelRun(runId).then(setRun)}
              >
                <Ban size={16} />
                安全取消
              </button>
            ) : null}
            {run?.status === "done" && run.result_file ? (
              <button
                className="button primary"
                onClick={() =>
                  navigate(`/results?file=${encodeURIComponent(run.result_file!)}`)
                }
              >
                <FolderOpen size={16} />
                查看研究档案 →
              </button>
            ) : null}
          </>
        }
      />
      {error ? <ErrorNotice message={error} /> : null}
      {run?.status === "failed" && run.error ? (
        <ErrorNotice message={`回测失败：${run.error}`} />
      ) : null}
      <div className="metric-grid live-metrics">
        <Metric
          label="事件连接"
          value={statusLabel(socketState)}
          note={<><Radio size={13} /> 自动重连并按序去重</>}
          tone={socketState === "live" ? "positive" : "warning"}
        />
        <Metric label="事件数量" value={eventCount} note="按事件序号去重" />
        <Metric label="执行者数量" value={run?.agents?.length ?? "—"} note="账户相互隔离" />
      </div>
      <div className="live-layout-v2">
        <OfficeFloor
          agents={visibleAgents}
          latestEvent={latest}
          runContext={runContext}
        />
        <div className="lp-rail">
          <LivePerformance
            context={runContext}
            returnsPct={returnsPct}
            eventsPerSecond={eventsPerSecond}
          />
          <aside className="event-stream panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">事件日志</span>
                <h2>决策事件流</h2>
              </div>
              <span className="status-chip">{eventCount} 条事件</span>
            </div>
            <div className="lp-stream-toolbar">
              <div className="lp-chips" role="group" aria-label="按类型过滤">
                {GROUP_ORDER.map((group) => (
                  <button
                    key={group}
                    className={`lp-chip${groupFilter === group ? " active" : ""}`}
                    onClick={() => setGroupFilter(group)}
                  >
                    {EVENT_GROUP_LABELS[group]}
                  </button>
                ))}
              </div>
              <div className="lp-stream-controls">
                {visibleAgents.length > 1 ? (
                  <select
                    className="lp-select"
                    aria-label="按智能体过滤"
                    value={agentFilter}
                    onChange={(event) => setAgentFilter(event.target.value)}
                  >
                    <option value="all">全部智能体</option>
                    {visibleAgents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                ) : null}
                <button
                  className={`lp-pause${paused ? " active" : ""}`}
                  aria-pressed={paused}
                  onClick={() => setPaused((current) => !current)}
                >
                  {paused ? <Play size={13} /> : <Pause size={13} />}
                  {paused ? "恢复滚动" : "暂停滚动"}
                </button>
              </div>
            </div>
            <div className="lp-stream-body">
              {paused && pendingCount > 0 ? (
                <button className="lp-new-pill" onClick={() => setPaused(false)}>
                  +{pendingCount} 条新事件，点击恢复
                </button>
              ) : null}
              <ol>
                {visibleEvents.map((event) => {
                  const owner = eventAgentId(event);
                  return (
                    <li key={event.sequence}>
                      <span className={`event-dot ${event.type}`} />
                      <div>
                        <strong>{eventLabel(event)}</strong>
                        <small>
                          #{event.sequence} · {String(event.data.date ?? "运行时")}
                          {owner ? (
                            <span className="event-agent">{agentNames.get(owner) ?? owner}</span>
                          ) : null}
                        </small>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
