import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Showcase } from "./Showcase";

vi.mock("../api", () => ({
  api: { maskingShowcase: vi.fn() },
}));

import { api } from "../api";

const payload = {
  schema_version: 1,
  experiment_id: "pilot",
  status: "complete" as const,
  title: "Masked vs Unmasked",
  summary: "Recorded comparison.",
  model: "deepseek-chat",
  window: { start: "2024-03-14", end: "2024-03-14" },
  repetitions: 1,
  commit: "abcdef123456",
  conditions: {
    masked: {
      label: "Masked",
      mask_dates: true,
      mask_entities: true,
      audit: { status: "pass", finding_count: 0 },
      metrics: { total_return_pct: 1, alpha_pct: 0.5 },
      runs: [{ id: "masked-r01", repetition: 1, metrics: { total_return_pct: 1 }, llm_total_tokens: 10 }],
      equity_curve: [["2024-03-14", 1_010_000]] as Array<[string, number]>,
    },
    unmasked: {
      label: "Unmasked control",
      mask_dates: false,
      mask_entities: false,
      audit: { status: "expected_findings_for_control", finding_count: 2 },
      metrics: { total_return_pct: 2, alpha_pct: 1.5 },
      runs: [{ id: "unmasked-r01", repetition: 1, metrics: { total_return_pct: 2 }, llm_total_tokens: 12 }],
      equity_curve: [["2024-03-14", 1_020_000]] as Array<[string, number]>,
    },
  },
  paired_deltas: { total_return_pct: 1 },
  limitations: ["Descriptive pilot only."],
};

describe("Showcase", () => {
  beforeEach(() => {
    vi.mocked(api.maskingShowcase).mockResolvedValue(payload);
  });

  it("explains the recorded experiment and switches conditions", async () => {
    render(<Showcase />);
    expect(await screen.findByText("Recorded experiment — not a live backtest")).toBeVisible();
    expect(screen.getByText("Leakage audit passed · 0 findings")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Unmasked control" }));

    expect(screen.getByText("2 findings retained for the explicit control")).toBeVisible();
    expect(screen.getByText("unmasked-r01")).toBeVisible();
  });
});
