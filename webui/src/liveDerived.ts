import type { LiveEvent } from "./types";

/**
 * 实时运行页的纯派生逻辑。
 *
 * LiveRun 组件只负责事件采集与渲染，所有"从事件序列推导界面状态"的计算
 * 都集中在这里，便于脱离 React 做确定性单测。
 */

/** 多智能体曲线 / 色点的固定调色板，按 agents 数组下标循环取用。 */
export const AGENT_COLORS = [
  "#48d597",
  "#5b8def",
  "#e0a63d",
  "#e2547a",
  "#8b6fe0",
  "#3dc7c0",
  "#d97757",
  "#6fd0e8",
];

export interface RunContextAgent {
  id: string;
  name: string;
  color: string;
}

export type RunContextStatus = "idle" | "running" | "done" | "failed" | "cancelled";

/**
 * 与像素办公室（pixel-office）共享的运行上下文契约。
 * `equity` 中每个智能体是一条按交易日累积的 [日期, 净值] 序列。
 */
export interface RunContext {
  status: RunContextStatus;
  date: string | null;
  /** 最近一个已完成交易日的 0 基下标；尚未完成任何交易日时为 -1。 */
  dayIndex: number;
  totalDays: number;
  agents: RunContextAgent[];
  equity: Record<string, Array<[date: string, equity: number]>>;
}

/** 事件流过滤分组。 */
export type EventGroup = "all" | "phase" | "tool" | "order" | "error" | "think";

export const EVENT_GROUP_TYPES: Record<Exclude<EventGroup, "all">, readonly string[]> = {
  phase: ["phase_change", "day_start", "day_end"],
  tool: ["tool_call"],
  order: ["order_placed"],
  error: ["run_error", "error"],
  think: ["llm_response", "llm_request"],
};

export const EVENT_GROUP_LABELS: Record<EventGroup, string> = {
  all: "全部",
  phase: "阶段",
  tool: "工具",
  order: "订单",
  error: "错误",
  think: "思考",
};

export interface EventFilter {
  types: EventGroup;
  /** "all" 表示全部智能体。 */
  agentId: string;
}

/** 提取事件的归属智能体；部分事件把 agent_id 放在嵌套的 trade 里。 */
export function eventAgentId(event: LiveEvent): string {
  const direct = event.data.agent_id;
  if (typeof direct === "string" && direct) return direct;
  const trade = event.data.trade as Record<string, unknown> | undefined;
  if (trade && typeof trade.agent_id === "string") return trade.agent_id;
  return "";
}

function mapStatus(runStatus?: string | null): RunContextStatus {
  switch (runStatus) {
    case "done":
      return "done";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "running":
    case "cancelling":
      return "running";
    default:
      return "idle";
  }
}

function pushEquityPoint(
  series: Array<[string, number]>,
  date: string,
  equity: number,
): void {
  // 重连重放可能让同一天的 day_end 出现两次；同一天只保留最新值。
  const last = series.at(-1);
  if (last && last[0] === date) {
    last[1] = equity;
    return;
  }
  const existing = series.findIndex(([pointDate]) => pointDate === date);
  if (existing >= 0) {
    series[existing] = [date, equity];
    return;
  }
  series.push([date, equity]);
}

/**
 * 从事件序列累积出运行上下文：每个智能体的净值曲线、最新交易日、
 * 进度下标与状态映射。
 *
 * day_end 优先提供 dayIndex / totalDays；尚未到达首个 day_end 时回退到
 * run_start.total_days。equity 中出现的、但 agents 参数里没有的智能体
 * 会被追加到 agents 列表（按发现顺序取色），保证曲线不会丢序列。
 */
export function buildRunContext(
  events: readonly LiveEvent[],
  agents: readonly { id: string; name: string }[],
  runStatus?: string | null,
): RunContext {
  const contextAgents: RunContextAgent[] = agents.map((agent, index) => ({
    id: agent.id,
    name: agent.name,
    color: AGENT_COLORS[index % AGENT_COLORS.length],
  }));
  const colorOf = new Map(contextAgents.map((agent) => [agent.id, agent.color]));
  const ensureAgent = (id: string) => {
    if (colorOf.has(id)) return;
    const color = AGENT_COLORS[contextAgents.length % AGENT_COLORS.length];
    contextAgents.push({ id, name: id, color });
    colorOf.set(id, color);
  };

  const equity: Record<string, Array<[string, number]>> = {};
  let date: string | null = null;
  let dayIndex = -1;
  let totalDays = 0;

  for (const event of events) {
    if (event.type === "run_start") {
      const total = Number(event.data.total_days ?? 0);
      if (Number.isFinite(total) && total > 0) totalDays = total;
      continue;
    }
    if (event.type === "day_start") {
      const day = event.data.date;
      if (typeof day === "string" && day) date = day;
      continue;
    }
    if (event.type !== "day_end") continue;
    const day = event.data.date;
    const dateKey = typeof day === "string" && day ? day : (date ?? "");
    if (typeof day === "string" && day) date = day;
    if (typeof event.data.day_index === "number") dayIndex = event.data.day_index;
    const total = Number(event.data.total_days ?? 0);
    if (Number.isFinite(total) && total > 0) totalDays = total;
    const snapshots = event.data.equity;
    if (!snapshots || typeof snapshots !== "object") continue;
    for (const [agentId, snapshot] of Object.entries(
      snapshots as Record<string, { equity?: unknown }>,
    )) {
      const value = Number(snapshot?.equity);
      if (!Number.isFinite(value) || !dateKey) continue;
      ensureAgent(agentId);
      const series = (equity[agentId] ??= []);
      pushEquityPoint(series, dateKey, value);
    }
  }

  return {
    status: mapStatus(runStatus),
    date,
    dayIndex,
    totalDays,
    agents: contextAgents,
    equity,
  };
}

/**
 * 事件流过滤：先按类型分组过滤，再按智能体过滤。
 * 没有归属智能体的事件（data.agent_id 缺失）视为全局事件，只在
 * "全部智能体"视图出现，不会重复计入每个智能体的视图。
 */
export function filterEvents(
  events: readonly LiveEvent[],
  filter: EventFilter,
): LiveEvent[] {
  const group = filter.types === "all" ? null : new Set(EVENT_GROUP_TYPES[filter.types]);
  return events.filter((event) => {
    if (group && !group.has(event.type)) return false;
    if (filter.agentId !== "all" && eventAgentId(event) !== filter.agentId) return false;
    return true;
  });
}

/**
 * 近 windowMs 毫秒窗口内的事件速率（条/秒）。
 * 以窗口内最新事件的时间戳为锚点（而不是 Date.now()），
 * 让结果对暂停、重放和测试都是确定性的。后端 ts 是 epoch 秒，
 * 这里对秒 / 毫秒两种单位做了兼容。
 */
export function eventRate(events: readonly LiveEvent[], windowMs: number): number {
  if (!events.length || windowMs <= 0) return 0;
  const toMs = (ts: number) => (ts < 1e12 ? ts * 1000 : ts);
  const latest = Math.max(...events.map((event) => toMs(event.ts)));
  const cutoff = latest - windowMs;
  const count = events.reduce(
    (total, event) => (toMs(event.ts) >= cutoff ? total + 1 : total),
    0,
  );
  return count / (windowMs / 1000);
}
