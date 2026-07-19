import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { AgentCard, RunState } from "../types";
import { LiveRun } from "./LiveRun";

vi.mock("../api", () => ({
  api: {
    agents: vi.fn(),
    run: vi.fn(),
    runs: vi.fn(),
    startDemo: vi.fn(),
    cancelRun: vi.fn(),
  },
  eventSocketUrl: (runId: string) => `ws://test/${runId}`,
}));

const mockedApi = vi.mocked(api);

// OfficeFloor renders a pixel-art canvas the office simulation drives via
// requestAnimationFrame; jsdom has no real 2D context, so stub just enough
// of it to avoid crashing the redirect test, which doesn't care about pixels.
function fakeCanvasContext() {
  const store: Record<string, unknown> = {
    measureText: () => ({ width: 0 }),
    createRadialGradient: () => ({ addColorStop: () => {} }),
    createLinearGradient: () => ({ addColorStop: () => {} }),
  };
  return new Proxy(store, {
    get(target, prop) {
      if (prop in target) return target[prop as string];
      return () => {};
    },
    set(target, prop, value) {
      target[prop as string] = value;
      return true;
    },
  });
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  close() {}
}

function emit(socket: FakeWebSocket, sequence: number, type: string, data: Record<string, unknown>) {
  socket.onmessage?.({ data: JSON.stringify({ sequence, type, ts: 1_720_000_000, data }) });
}

describe("LiveRun", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      fakeCanvasContext() as unknown as CanvasRenderingContext2D,
    );
    localStorage.clear();
    vi.clearAllMocks();
    mockedApi.agents.mockResolvedValue([]);
    mockedApi.runs.mockResolvedValue([]);
  });

  it("stays on the page after the run finishes and offers an archive button", async () => {
    mockedApi.run
      .mockResolvedValueOnce({ id: "run-1", status: "running", created_at: "2026-07-17T00:00:00Z", agents: [] })
      .mockResolvedValueOnce({
        id: "run-1",
        status: "done",
        created_at: "2026-07-17T00:00:00Z",
        result_file: "20260717_result.json",
        agents: [],
      });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
          <Route path="/results" element={<div>RESULTS_PAGE</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeTruthy();

    await act(async () => {
      emit(socket, 1, "run_end", {});
    });

    // 不再自动跳转；出现高亮主按钮，点击才进入研究档案。
    const archive = await screen.findByRole("button", { name: /查看研究档案/ });
    expect(screen.queryByText("RESULTS_PAGE")).not.toBeInTheDocument();
    expect(mockedApi.run).toHaveBeenCalledTimes(2);

    fireEvent.click(archive);
    await screen.findByText("RESULTS_PAGE");
  });

  it("shows live progress and per-agent equity in the performance panel", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: ["alpha", "beta"],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      emit(socket, 1, "day_end", {
        date: "2024-03-04",
        day_index: 4,
        total_days: 20,
        equity: {
          alpha: { equity: 1_050_000, return_pct: 5 },
          beta: { equity: 940_000, return_pct: -6 },
        },
      });
    });

    const panel = screen.getByLabelText("实时绩效");
    expect(within(panel).getByText(/第 5 \/ 20 个交易日/)).toBeInTheDocument();
    expect(within(panel).getByText(/当前日期 2024\/03\/04/)).toBeInTheDocument();
    expect(within(panel).getByText("alpha")).toBeInTheDocument();
    expect(within(panel).getByText("1,050,000")).toBeInTheDocument();
    expect(within(panel).getByText("+5.00%")).toBeInTheDocument();
    expect(within(panel).getByText("-6.00%")).toBeInTheDocument();
    // 净值曲线（含两条序列）。
    expect(within(panel).getByLabelText("各智能体净值曲线")).toBeInTheDocument();
  });

  it("filters the event log by type chips", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: ["alpha"],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      emit(socket, 1, "phase_change", { phase: "pre_market", date: "2024-03-04" });
      emit(socket, 2, "tool_call", { agent_id: "alpha", tool: "get_kline", date: "2024-03-04" });
    });

    expect(screen.getByText(/盘前阶段/)).toBeInTheDocument();
    expect(screen.getByText(/get_kline/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "工具" }));
    expect(screen.queryByText(/盘前阶段/)).not.toBeInTheDocument();
    expect(screen.getByText(/get_kline/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部" }));
    expect(screen.getByText(/盘前阶段/)).toBeInTheDocument();
  });

  it("filters the event log by agent via the dropdown", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: ["alpha", "beta"],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      emit(socket, 1, "tool_call", { agent_id: "alpha", tool: "get_kline", date: "2024-03-04" });
      emit(socket, 2, "tool_call", { agent_id: "beta", tool: "get_news", date: "2024-03-04" });
    });

    expect(screen.getByText(/get_kline/)).toBeInTheDocument();
    expect(screen.getByText(/get_news/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("按智能体过滤"), { target: { value: "beta" } });
    expect(screen.queryByText(/get_kline/)).not.toBeInTheDocument();
    expect(screen.getByText(/get_news/)).toBeInTheDocument();
  });

  it("pauses the stream, accumulates a backlog pill, and resumes on click", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: ["alpha"],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      emit(socket, 1, "tool_call", { agent_id: "alpha", tool: "get_kline", date: "2024-03-04" });
    });
    expect(screen.getByText(/get_kline/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /暂停滚动/ }));

    await act(async () => {
      emit(socket, 2, "tool_call", { agent_id: "alpha", tool: "get_news", date: "2024-03-04" });
      emit(socket, 3, "tool_call", { agent_id: "alpha", tool: "get_portfolio", date: "2024-03-04" });
    });

    // 暂停期间新事件不渲染，列表上方浮出积压 pill。
    expect(screen.queryByText(/get_news/)).not.toBeInTheDocument();
    expect(screen.queryByText(/get_portfolio/)).not.toBeInTheDocument();
    const pill = screen.getByRole("button", { name: /\+2 条新事件，点击恢复/ });
    fireEvent.click(pill);

    expect(screen.getByText(/get_news/)).toBeInTheDocument();
    expect(screen.getByText(/get_portfolio/)).toBeInTheDocument();
  });

  it("deduplicates replayed events by sequence", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: [],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    const socket = FakeWebSocket.instances[0];
    const payload = JSON.stringify({
      sequence: 7,
      type: "tool_call",
      ts: 1_720_000_000,
      data: { tool: "get_kline", date: "2024-03-04" },
    });
    await act(async () => {
      socket.onmessage?.({ data: payload });
      socket.onmessage?.({ data: payload });
    });

    expect(screen.getAllByText(/get_kline/)).toHaveLength(1);
  });

  it("surfaces a failed run with its error message", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "failed",
      created_at: "2026-07-17T00:00:00Z",
      error: "ReplayMismatchError: request 12 diverged",
      agents: [],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    expect(await screen.findByText(/回测失败：ReplayMismatchError/)).toBeInTheDocument();
  });

  it("does not offer the archive button while the run is still in progress", async () => {
    mockedApi.run.mockResolvedValue({
      id: "run-1",
      status: "running",
      created_at: "2026-07-17T00:00:00Z",
      agents: [],
    });

    render(
      <MemoryRouter initialEntries={["/live?run=run-1"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
          <Route path="/results" element={<div>RESULTS_PAGE</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/回测控制室/i);
    expect(screen.queryByText("RESULTS_PAGE")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /查看研究档案/ })).not.toBeInTheDocument();
  });

  it("auto-opens the most recent active run when no run id is given", async () => {
    mockedApi.runs.mockResolvedValue([
      { id: "run-old", status: "done", created_at: "2026-07-17T00:00:00Z", agents: [] },
      { id: "run-new", status: "running", created_at: "2026-07-18T00:00:00Z", agents: [] },
    ]);
    mockedApi.run.mockResolvedValue({
      id: "run-new",
      status: "running",
      created_at: "2026-07-18T00:00:00Z",
      agents: [],
    });

    render(
      <MemoryRouter initialEntries={["/live"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    // 不需要手输 ID：自动选中仍在运行的 run-new（优先于已完成的）。
    await vi.waitFor(() => expect(mockedApi.run).toHaveBeenCalledWith("run-new"));
    await screen.findByText(/回测控制室/i);
    expect(localStorage.getItem("traderharness.activeRun")).toBe("run-new");
  });

  it("shows the standby office and launches the demo without typing an id", async () => {
    mockedApi.agents.mockResolvedValue([
      { id: "alpha", name: "Alpha" } as unknown as AgentCard,
    ]);
    mockedApi.startDemo.mockResolvedValue({
      id: "run-demo",
      status: "running",
      created_at: "2026-07-18T00:00:00Z",
      agents: ["alpha"],
    });
    mockedApi.run.mockResolvedValue({
      id: "run-demo",
      status: "running",
      created_at: "2026-07-18T00:00:00Z",
      agents: ["alpha"],
    });

    render(
      <MemoryRouter initialEntries={["/live"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    // 空闲时像素办公室直接可见，无需任何运行 ID。
    expect(await screen.findByLabelText("智能体实时运行大厅")).toBeInTheDocument();
    expect(await screen.findByText("暂无运行记录")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /运行免密演示/ }));
    await vi.waitFor(() => expect(mockedApi.run).toHaveBeenCalledWith("run-demo"));
    await screen.findByText(/回测控制室/i);
  });

  it("falls back to the latest run when the remembered run id is stale", async () => {
    localStorage.setItem("traderharness.activeRun", "ghost-run");
    mockedApi.run.mockImplementation((id: string) =>
      id === "ghost-run"
        ? Promise.reject(new Error("未找到回测运行"))
        : Promise.resolve({
            id,
            status: "running",
            created_at: "2026-07-18T00:00:00Z",
            agents: [],
          } as RunState),
    );
    mockedApi.runs.mockResolvedValue([
      { id: "run-new", status: "running", created_at: "2026-07-18T00:00:00Z", agents: [] },
    ]);

    render(
      <MemoryRouter initialEntries={["/live"]}>
        <Routes>
          <Route path="/live" element={<LiveRun />} />
        </Routes>
      </MemoryRouter>,
    );

    // 服务重启后旧 ID 失效：自动改开最近的 run-new，而不是困在报错页。
    await vi.waitFor(() => expect(mockedApi.run).toHaveBeenCalledWith("run-new"));
    await screen.findByText(/回测控制室/i);
    expect(localStorage.getItem("traderharness.activeRun")).toBe("run-new");
  });
});
