import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AnalyzedAgent } from "../types";
import { TradeReviewWorkbench } from "./TradeReviewWorkbench";

const agent = {
  metrics: {},
  behavior: {},
  vs_benchmark: {},
  daily: [],
  days: [],
  tool_usage: [],
  trades: [],
  securities: {},
  reasoning_coverage: { responses: 1, with_reasoning: 1 },
  decisions: [
    {
      date: "2024-03-14",
      step: 3,
      phase: "open_window",
      sub_window: "open_1",
      content: "量价确认，按计划建立仓位。",
      reasoning: "突破有效，但仓位必须控制在上限内。",
      tool_calls: [],
    },
  ],
  tools: [
    {
      date: "2024-03-14",
      step: 4,
      name: "place_order",
      args: { stock_code: "000777", action: "buy", quantity: 1000 },
      result: { success: true, price: 10.5 },
    },
  ],
  trade_reviews: [
    {
      id: "trade-1",
      code: "000777",
      trade: {
        trade_date: "2024-03-14",
        stock_code: "000777",
        action: "buy",
        price: 10.5,
        quantity: 1000,
        signal_reasoning: "趋势确认",
        window: "open_1",
      },
      marker: {
        date: "2024-03-14",
        side: "buy",
        price: 10.5,
        quantity: 1000,
        reasoning: "趋势确认",
        window: "open_1",
      },
      bars: [
        { date: "2024-03-13", open: 10, high: 10.6, low: 9.9, close: 10.5, volume: 1800 },
      ],
      decision_indices: [0],
      order_tool_index: 0,
      evidence_status: "complete",
    },
  ],
} satisfies AnalyzedAgent;

describe("TradeReviewWorkbench", () => {
  it("keeps the selected fill, K-line, and decision chain in one view", () => {
    render(<TradeReviewWorkbench agent={agent} />);

    fireEvent.click(screen.getByRole("button", { name: /000777/i }));

    expect(screen.getByRole("img", { name: /K 线图/i })).toBeInTheDocument();
    expect(screen.getByText("趋势确认")).toBeInTheDocument();
    expect(screen.getByText("突破有效，但仓位必须控制在上限内。")).toBeInTheDocument();
    expect(screen.getByText(/place_order/i)).toBeInTheDocument();
  });

  it("marks evaluation-only bars as post-hoc, not agent-visible", () => {
    const withEvaluationBars = {
      ...agent,
      trade_reviews: [
        {
          ...agent.trade_reviews[0],
          bars_source: "evaluation" as const,
          bars: [
            { date: "2024-03-13", open: 10, high: 10.6, low: 9.9, close: 10.5, volume: 1800, source: "evaluation" as const },
          ],
        },
      ],
    } satisfies AnalyzedAgent;

    render(<TradeReviewWorkbench agent={withEvaluationBars} />);

    expect(screen.getByText(/智能体当时未查看该 K 线/i)).toBeInTheDocument();
  });

  it("labels legacy artifacts instead of inventing missing reasoning", () => {
    const legacy = {
      ...agent,
      reasoning_coverage: { responses: 1, with_reasoning: 0 },
      decisions: [{ ...agent.decisions[0], reasoning: "" }],
    } satisfies AnalyzedAgent;

    render(<TradeReviewWorkbench agent={legacy} />);

    expect(screen.getByText(/系统不会伪造缺失的隐藏推理/i)).toBeInTheDocument();
    expect(screen.getByText(/未记录独立推理内容/i)).toBeInTheDocument();
  });
});
