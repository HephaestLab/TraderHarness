import { describe, expect, it } from "vitest";
import {
  AGENT_COLORS,
  buildRunContext,
  eventAgentId,
  eventRate,
  filterEvents,
} from "./liveDerived";
import type { LiveEvent } from "./types";

let sequence = 0;
function event(type: string, data: Record<string, unknown> = {}, ts = 0): LiveEvent {
  sequence += 1;
  return { sequence, type, ts, data };
}

describe("buildRunContext", () => {
  it("returns an idle empty context for no events", () => {
    const context = buildRunContext(
      [],
      [
        { id: "alpha", name: "阿尔法" },
        { id: "beta", name: "贝塔" },
      ],
      null,
    );
    expect(context.status).toBe("idle");
    expect(context.date).toBeNull();
    expect(context.dayIndex).toBe(-1);
    expect(context.totalDays).toBe(0);
    expect(context.equity).toEqual({});
    expect(context.agents).toEqual([
      { id: "alpha", name: "阿尔法", color: AGENT_COLORS[0] },
      { id: "beta", name: "贝塔", color: AGENT_COLORS[1] },
    ]);
  });

  it("maps run statuses onto the context status", () => {
    expect(buildRunContext([], [], "running").status).toBe("running");
    expect(buildRunContext([], [], "cancelling").status).toBe("running");
    expect(buildRunContext([], [], "done").status).toBe("done");
    expect(buildRunContext([], [], "failed").status).toBe("failed");
    expect(buildRunContext([], [], "cancelled").status).toBe("cancelled");
    expect(buildRunContext([], [], undefined).status).toBe("idle");
  });

  it("falls back to run_start.total_days before the first day_end", () => {
    const context = buildRunContext(
      [event("run_start", { start_date: "2024-01-02", end_date: "2024-02-02", total_days: 20 })],
      [],
      "running",
    );
    expect(context.totalDays).toBe(20);
    expect(context.dayIndex).toBe(-1);
    expect(context.date).toBeNull();
  });

  it("tracks the current date from day_start and day_end events", () => {
    const context = buildRunContext(
      [
        event("run_start", { total_days: 3 }),
        event("day_start", { date: "2024-01-02" }),
        event("day_end", {
          date: "2024-01-02",
          day_index: 0,
          total_days: 3,
          equity: { alpha: { equity: 1_010_000, return_pct: 1 } },
        }),
        event("day_start", { date: "2024-01-03" }),
      ],
      [{ id: "alpha", name: "阿尔法" }],
      "running",
    );
    expect(context.date).toBe("2024-01-03");
    expect(context.dayIndex).toBe(0);
    expect(context.totalDays).toBe(3);
  });

  it("accumulates per-agent equity series across day_end events", () => {
    const context = buildRunContext(
      [
        event("day_end", {
          date: "2024-01-02",
          day_index: 0,
          total_days: 2,
          equity: {
            alpha: { equity: 1_010_000, return_pct: 1 },
            beta: { equity: 990_000, return_pct: -1 },
          },
        }),
        event("day_end", {
          date: "2024-01-03",
          day_index: 1,
          total_days: 2,
          equity: {
            alpha: { equity: 1_030_000, return_pct: 3 },
            beta: { equity: 985_000, return_pct: -1.5 },
          },
        }),
      ],
      [
        { id: "alpha", name: "阿尔法" },
        { id: "beta", name: "贝塔" },
      ],
      "running",
    );
    expect(context.equity.alpha).toEqual([
      ["2024-01-02", 1_010_000],
      ["2024-01-03", 1_030_000],
    ]);
    expect(context.equity.beta).toEqual([
      ["2024-01-02", 990_000],
      ["2024-01-03", 985_000],
    ]);
    expect(context.dayIndex).toBe(1);
  });

  it("keeps only the latest value when a replay repeats the same day", () => {
    const context = buildRunContext(
      [
        event("day_end", {
          date: "2024-01-02",
          day_index: 0,
          total_days: 2,
          equity: { alpha: { equity: 1_000_000 } },
        }),
        event("day_end", {
          date: "2024-01-02",
          day_index: 0,
          total_days: 2,
          equity: { alpha: { equity: 1_000_001 } },
        }),
      ],
      [{ id: "alpha", name: "阿尔法" }],
      "running",
    );
    expect(context.equity.alpha).toEqual([["2024-01-02", 1_000_001]]);
  });

  it("appends agents discovered in equity payloads with the next palette color", () => {
    const context = buildRunContext(
      [
        event("day_end", {
          date: "2024-01-02",
          day_index: 0,
          total_days: 1,
          equity: { ghost: { equity: 1_000_000 } },
        }),
      ],
      [{ id: "alpha", name: "阿尔法" }],
      "running",
    );
    expect(context.agents.map((agent) => agent.id)).toEqual(["alpha", "ghost"]);
    expect(context.agents[1].color).toBe(AGENT_COLORS[1]);
    expect(context.equity.ghost).toEqual([["2024-01-02", 1_000_000]]);
  });

  it("ignores malformed equity payloads", () => {
    const context = buildRunContext(
      [
        event("day_end", { date: "2024-01-02", day_index: 0, total_days: 1 }),
        event("day_end", {
          date: "2024-01-03",
          day_index: 1,
          total_days: 2,
          equity: { alpha: { equity: "not-a-number" } },
        }),
      ],
      [{ id: "alpha", name: "阿尔法" }],
      "running",
    );
    expect(context.equity.alpha ?? []).toEqual([]);
    expect(context.dayIndex).toBe(1);
  });
});

describe("filterEvents", () => {
  const events = [
    event("phase_change", { phase: "pre_market" }),
    event("day_start", { date: "2024-01-02" }),
    event("tool_call", { agent_id: "alpha", tool: "get_kline" }),
    event("tool_call", { agent_id: "beta", tool: "get_news" }),
    event("order_placed", { agent_id: "alpha", side: "buy" }),
    event("llm_response", { agent_id: "alpha" }),
    event("llm_request", { agent_id: "beta" }),
    event("run_error", { error: "boom" }),
    event("day_end", { date: "2024-01-02", day_index: 0, total_days: 1 }),
  ];

  it("returns every event for the 'all' group", () => {
    expect(filterEvents(events, { types: "all", agentId: "all" })).toHaveLength(events.length);
  });

  it("groups phase events (phase_change / day_start / day_end)", () => {
    const filtered = filterEvents(events, { types: "phase", agentId: "all" });
    expect(filtered.map((item) => item.type)).toEqual(["phase_change", "day_start", "day_end"]);
  });

  it("groups tool / order / error / think events", () => {
    expect(
      filterEvents(events, { types: "tool", agentId: "all" }).map((item) => item.type),
    ).toEqual(["tool_call", "tool_call"]);
    expect(
      filterEvents(events, { types: "order", agentId: "all" }).map((item) => item.type),
    ).toEqual(["order_placed"]);
    expect(
      filterEvents(events, { types: "error", agentId: "all" }).map((item) => item.type),
    ).toEqual(["run_error"]);
    expect(
      filterEvents(events, { types: "think", agentId: "all" }).map((item) => item.type),
    ).toEqual(["llm_response", "llm_request"]);
  });

  it("filters by agent and keeps global events only in the all-agents view", () => {
    const alpha = filterEvents(events, { types: "all", agentId: "alpha" });
    expect(alpha.map((item) => item.type)).toEqual(["tool_call", "order_placed", "llm_response"]);
    // 无 agent_id 的全局事件（phase_change / day_start / day_end / run_error）
    // 只出现在"全部智能体"视图。
    const all = filterEvents(events, { types: "all", agentId: "all" });
    expect(all.map((item) => item.type)).toContain("phase_change");
  });

  it("combines group and agent filters", () => {
    const filtered = filterEvents(events, { types: "tool", agentId: "beta" });
    expect(filtered).toHaveLength(1);
    expect(filtered[0].data.tool).toBe("get_news");
  });

  it("recognizes agent ids nested inside trade payloads", () => {
    const tradeEvent = event("order_placed", { trade: { agent_id: "gamma", side: "sell" } });
    expect(eventAgentId(tradeEvent)).toBe("gamma");
    expect(
      filterEvents([tradeEvent], { types: "all", agentId: "gamma" }),
    ).toHaveLength(1);
  });
});

describe("eventRate", () => {
  it("returns 0 for empty streams and non-positive windows", () => {
    expect(eventRate([], 10_000)).toBe(0);
    expect(eventRate([event("tool_call", {}, 100)], 0)).toBe(0);
  });

  it("counts only events inside the trailing window (epoch seconds)", () => {
    const base = 1_720_000_000; // epoch 秒
    const events = [
      event("tool_call", {}, base - 30), // 窗口外
      event("tool_call", {}, base - 9),
      event("tool_call", {}, base - 5),
      event("tool_call", {}, base),
    ];
    // 10 秒窗口内 3 条 → 0.3 条/秒
    expect(eventRate(events, 10_000)).toBeCloseTo(0.3);
  });

  it("also accepts millisecond timestamps", () => {
    const base = 1_720_000_000_000; // epoch 毫秒
    const events = [
      event("tool_call", {}, base - 30_000),
      event("tool_call", {}, base - 1_000),
      event("tool_call", {}, base),
    ];
    expect(eventRate(events, 10_000)).toBeCloseTo(0.2);
  });

  it("anchors on the latest event rather than wall-clock time", () => {
    const events = [
      event("tool_call", {}, 100),
      event("tool_call", {}, 104),
      event("tool_call", {}, 109),
    ];
    // 以最新事件为锚点的 10 秒窗口覆盖全部 3 条。
    expect(eventRate(events, 10_000)).toBeCloseTo(0.3);
    // 5 秒窗口只覆盖 ts=104 与 ts=109 两条。
    expect(eventRate(events, 5_000)).toBeCloseTo(0.4);
  });
});
