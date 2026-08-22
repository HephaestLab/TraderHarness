import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { AgentCard, PaperSession } from "../types";
import { PaperTrading } from "./PaperTrading";

vi.mock("../api", () => ({
  api: {
    agents: vi.fn(),
    paperSessions: vi.fn(),
    paperSession: vi.fn(),
    startPaper: vi.fn(),
    cancelPaper: vi.fn(),
  },
  paperEventSocketUrl: (id: string) => `ws://test/paper/${id}`,
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) { FakeWebSocket.instances.push(this); }
  close() {}
}

const mockedApi = vi.mocked(api);
const card = {
  id: "momentum-dragon",
  name: "动量龙头",
  model: "deepseek-chat",
} as AgentCard;
const secondCard = {
  id: "value-sage",
  name: "价值猎手",
  model: "deepseek-reasoner",
} as AgentCard;
const session: PaperSession = {
  id: "paper-1",
  status: "done",
  created_at: "2026-08-21T00:00:00Z",
  agent_id: card.id,
  agent_name: card.name,
  agent_ids: [card.id, secondCard.id],
  session_date: "2026-08-21",
  mode: "accelerated",
  initial_cash: 1_000_000,
  clock_state: "done",
  phase: "close_window",
  event_count: 8,
  account: { cash: 800_000, equity: 1_025_000, return_pct: 2.5 },
  positions: [{ stock_code: "600519", quantity: 100, last_price: 1500, unrealized_pnl: 5000 }],
  trades: [{ stock_code: "600519", action: "buy", quantity: 100, price: 1450 }],
  equity_curve: [
    ["2026-08-21T09:50:00+08:00", 1_000_000],
    ["2026-08-21T15:00:00+08:00", 1_025_000],
  ],
  quote_health: {
    source: "eastmoney_1m",
    granularity: "1m",
    missing_codes: [],
    one_minute_bars: 241,
    request_metrics: { requests: 4, rate_limited: 0 },
  },
  agents: [
    {
      agent_id: card.id,
      agent_name: card.name,
      model: card.model,
      status: "done",
      phase: "close_window",
      account: { cash: 800_000, equity: 1_025_000, return_pct: 2.5 },
      positions: [{ stock_code: "600519", quantity: 100, last_price: 1500, unrealized_pnl: 5000 }],
      trades: [{ stock_code: "600519", action: "buy", quantity: 100, price: 1450 }],
      equity_curve: [["2026-08-21T09:50:00+08:00", 1_000_000], ["2026-08-21T15:00:00+08:00", 1_025_000]],
      quote_health: { source: "eastmoney_1m", granularity: "1m", missing_codes: [], request_metrics: { rate_limited: 0 } },
    },
    {
      agent_id: secondCard.id,
      agent_name: secondCard.name,
      model: secondCard.model,
      status: "done",
      phase: "close_window",
      account: { cash: 900_000, equity: 990_000, return_pct: -1 },
      positions: [],
      trades: [],
      equity_curve: [["2026-08-21T09:50:00+08:00", 1_000_000], ["2026-08-21T15:00:00+08:00", 990_000]],
    },
  ],
  broadcasts: [
    {
      sequence: 6,
      type: "paper_market_pulse",
      ts: 1_777_000_000,
      data: { agent_id: card.id, advancers: 1, decliners: 0, as_of: "2026-08-21T10:00:00+08:00", items: [{ stock_code: "600519", stock_name: "贵州茅台", change_pct: 3.2, volume_ratio: 2.1, importance: "high" }] },
    },
    {
      sequence: 7,
      type: "paper_news",
      ts: 1_777_000_001,
      data: { agent_id: card.id, agent_name: card.name, items: [{ source_id: "n1", kind: "flash", importance: "high", time: "2026-08-21T10:01:00+08:00", title: "央行发布重要政策", content: "保持流动性合理充裕" }] },
    },
  ],
  last_event: null,
};

describe("PaperTrading", () => {
  beforeEach(() => {
    localStorage.clear();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.clearAllMocks();
    mockedApi.agents.mockResolvedValue([card, secondCard]);
    mockedApi.paperSessions.mockResolvedValue([session]);
    mockedApi.paperSession.mockResolvedValue(session);
  });

  it("shows account, quote health, trajectory and the trade/position tabs", async () => {
    render(
      <MemoryRouter initialEntries={["/paper?session=paper-1"]}>
        <Routes><Route path="/paper" element={<PaperTrading />} /></Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("多 Agent 每日模拟盘")).toBeInTheDocument();
    expect(await screen.findByText("¥ 1,025,000")).toBeInTheDocument();
    expect(screen.getAllByText("+2.50%")).toHaveLength(2);
    expect(screen.getByText(/限流 0 · 缺失 0/)).toBeInTheDocument();
    expect(screen.getByText("市场播报台")).toBeInTheDocument();
    expect(screen.getByText("央行发布重要政策")).toBeInTheDocument();
    expect(screen.getByText("贵州茅台")).toBeInTheDocument();

    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      socket.onmessage?.({
        data: JSON.stringify({
          sequence: 9,
          type: "tool_call",
          ts: 1_777_000_000,
          data: {
            agent_id: card.id,
            tool: "execute_code",
            args: { code: "prices = [10, 11]\nprint(sum(prices))" },
            result_preview: "{\"stdout\":\"21\"}",
          },
        }),
      });
    });
    expect(screen.getByText(/调用 执行 Python/)).toBeInTheDocument();
    expect(screen.getByLabelText("python 代码")).toHaveTextContent("print(sum(prices))");
    expect(screen.getByText("工具返回")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /交割/ }));
    expect(screen.getAllByText("600519").length).toBeGreaterThan(0);
    expect(screen.getByText("1,450")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /持仓/ }));
    expect(screen.getByText("1,500")).toBeInTheDocument();
    expect(screen.getByText("5,000")).toBeInTheDocument();
  });

  it("submits a selected multi-agent field", async () => {
    mockedApi.startPaper.mockResolvedValue(session);
    render(
      <MemoryRouter initialEntries={["/paper?session=paper-1"]}>
        <Routes><Route path="/paper" element={<PaperTrading />} /></Routes>
      </MemoryRouter>,
    );
    await screen.findByText("多 Agent 每日模拟盘");
    const valueAgent = (await screen.findAllByRole("button", { name: /价值猎手/ }))
      .find((button) => button.hasAttribute("aria-pressed"))!;
    expect(valueAgent).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(valueAgent);
    expect(screen.getByRole("button", { name: "启动 1 个 Agent" })).toBeInTheDocument();
    fireEvent.click(valueAgent);
    fireEvent.click(screen.getByRole("button", { name: "启动 2 个 Agent" }));
    expect(mockedApi.startPaper).toHaveBeenCalledWith(expect.objectContaining({
      agent_ids: [card.id, secondCard.id],
    }));
  });
});
