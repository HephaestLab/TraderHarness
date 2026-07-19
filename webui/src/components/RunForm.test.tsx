import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunForm } from "./RunForm";

const agents = [
  {
    id: "momentum",
    name: "Momentum",
    description: "Trend strategy",
    persona: "Trend mandate",
    strategy_tags: ["momentum"],
    risk_profile: "aggressive" as const,
    holding_period: "3-10 trading days",
    allowed_tools: ["get_portfolio", "get_position", "place_order", "finish_day"],
    model: "deepseek-chat",
    initial_cash: 1_000_000,
    max_positions: 4,
    max_position_pct: 25,
  },
  {
    id: "value",
    name: "Value",
    description: "Value strategy",
    persona: "Value mandate",
    strategy_tags: ["value"],
    risk_profile: "conservative" as const,
    holding_period: "20-60 trading days",
    allowed_tools: ["get_portfolio", "get_position", "place_order", "finish_day"],
    model: "deepseek-chat",
    initial_cash: 1_000_000,
    max_positions: 4,
    max_position_pct: 25,
  },
];

describe("RunForm", () => {
  it("enforces entity masking in submitted configuration", () => {
    const submit = vi.fn();
    render(<RunForm agents={agents} onSubmit={submit} />);
    fireEvent.click(screen.getByRole("button", { name: /开始回测/i }));
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        agents: ["momentum"],
        mask_entities: true,
        entity_mask_seed: 42,
      }),
    );
  });

  it("requires at least two agents for comparison", () => {
    render(<RunForm agents={agents} multiple onSubmit={vi.fn()} />);
    const submit = screen.getByRole("button", { name: /运行对比/i });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /value.*deepseek/i }));
    expect(submit).toBeEnabled();
  });
});
