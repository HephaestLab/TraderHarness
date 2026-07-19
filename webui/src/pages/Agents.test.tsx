import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { Agents } from "./Agents";

vi.mock("../api", () => ({
  api: {
    agents: vi.fn(),
    tools: vi.fn(),
    createAgent: vi.fn(),
    updateAgent: vi.fn(),
    deleteAgent: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

describe("Agents", () => {
  beforeEach(() => {
    mockedApi.agents.mockResolvedValue([
      {
        id: "momentum-dragon",
        name: "Momentum Dragon",
        description: "量价突破趋势交易。",
        persona: "遵循趋势确认、风险预算和退出纪律。",
        model: "deepseek-chat",
        initial_cash: 1_000_000,
        max_positions: 4,
        max_position_pct: 25,
        strategy_tags: ["momentum", "breakout"],
        risk_profile: "aggressive",
        holding_period: "3-10 trading days",
        allowed_tools: ["get_portfolio", "get_position", "place_order", "finish_day"],
        builtin: true,
      },
    ]);
    mockedApi.tools.mockResolvedValue([
      {
        name: "place_order",
        label: "下单",
        description: "执行订单。",
        category: "execution",
        required: true,
      },
      {
        name: "get_fundamentals",
        label: "基本面",
        description: "查询时间点安全的财务数据。",
        category: "fundamental",
        required: false,
      },
    ]);
  });

  it("uses structured controls and protected tool checkboxes", async () => {
    render(<Agents />);
    await screen.findByText("趋势龙");

    fireEvent.click(screen.getByRole("button", { name: /新建智能体/i }));

    expect(screen.getByRole("heading", { name: /定义交易职责/i })).toBeInTheDocument();
    const modelSelect = screen.getByRole("combobox", { name: /模型/i });
    expect(modelSelect).toBeInTheDocument();
    expect(modelSelect).toHaveValue("deepseek-v4-pro");
    const modelOptionLabels = within(modelSelect).getAllByRole("option").map((option) => option.textContent);
    expect(modelOptionLabels).toEqual(["DeepSeek V4 Pro", "DeepSeek V4 Flash"]);
    expect(modelOptionLabels.join()).not.toMatch(/deepseek-chat|deepseek-reasoner/i);
    expect(screen.getByText(/支持 thinking 深度推理/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /保守/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /下单.*place_order/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /下单.*place_order/i })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /基本面.*get_fundamentals/i })).not.toBeDisabled();

    await waitFor(() => expect(mockedApi.tools).toHaveBeenCalled());
  });
});
