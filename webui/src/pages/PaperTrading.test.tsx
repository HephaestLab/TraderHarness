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
const session: PaperSession = {
  id: "paper-1",
  status: "done",
  created_at: "2026-08-21T00:00:00Z",
  agent_id: card.id,
  agent_name: card.name,
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
  last_event: null,
};

describe("PaperTrading", () => {
  beforeEach(() => {
    localStorage.clear();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.clearAllMocks();
    mockedApi.agents.mockResolvedValue([card]);
    mockedApi.paperSessions.mockResolvedValue([session]);
    mockedApi.paperSession.mockResolvedValue(session);
  });

  it("shows account, quote health, trajectory and the trade/position tabs", async () => {
    render(
      <MemoryRouter initialEntries={["/paper?session=paper-1"]}>
        <Routes><Route path="/paper" element={<PaperTrading />} /></Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Agent 实盘演练场")).toBeInTheDocument();
    expect(await screen.findByText("¥ 1,025,000")).toBeInTheDocument();
    expect(screen.getAllByText("+2.50%")).toHaveLength(2);
    expect(screen.getByText(/限流 0 · 缺失 0/)).toBeInTheDocument();

    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      socket.onmessage?.({
        data: JSON.stringify({
          sequence: 9,
          type: "tool_call",
          ts: 1_777_000_000,
          data: { tool: "get_kline" },
        }),
      });
    });
    expect(screen.getByText(/调用/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /交割/ }));
    expect(screen.getByText("600519")).toBeInTheDocument();
    expect(screen.getByText("1,450")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /持仓/ }));
    expect(screen.getByText("1,500")).toBeInTheDocument();
    expect(screen.getByText("5,000")).toBeInTheDocument();
  });
});
