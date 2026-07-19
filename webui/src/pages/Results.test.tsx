import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { AnalyzedAgent, ResultAnalysis } from "../types";
import { Results } from "./Results";

vi.mock("../api", () => ({
  api: {
    results: vi.fn(),
    result: vi.fn(),
    resultAnalysis: vi.fn(),
    deleteResult: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

function emptyAgent(overrides: Partial<AnalyzedAgent["metrics"]>, dailyEquity: number): AnalyzedAgent {
  return {
    metrics: { total_return_pct: 0, sharpe_ratio: 0, max_drawdown_pct: 0, win_rate: 0, ...overrides },
    behavior: {},
    vs_benchmark: {},
    daily: [{ date: "2024-03-14", equity: dailyEquity, daily_return_pct: 0, drawdown_pct: 0 }],
    trades: [],
    days: [],
    decisions: [],
    reasoning_coverage: { responses: 0, with_reasoning: 0 },
    tools: [],
    tool_usage: [],
    securities: {},
    trade_reviews: [],
  };
}

function multiAgentAnalysis(): ResultAnalysis {
  return {
    status: "done",
    start_date: "2024-03-14",
    end_date: "2024-03-15",
    trading_days: 2,
    config: {},
    benchmark: { name: "CSI 300", daily: [] },
    agents: {
      momentum: emptyAgent({ total_return_pct: -1.0, sharpe_ratio: -0.4 }, 990_000),
      contrarian: emptyAgent({ total_return_pct: 4.0, sharpe_ratio: 1.8 }, 1_040_000),
    },
    comparison: {
      ranking: ["contrarian", "momentum"],
      best_agent_id: "contrarian",
      agents: [
        {
          agent_id: "contrarian",
          total_return_pct: 4.0,
          annual_return_pct: 0,
          sharpe_ratio: 1.8,
          max_drawdown_pct: -0.5,
          win_rate: 70,
          final_value: 1_040_000,
          trade_count: 0,
          rank: 1,
        },
        {
          agent_id: "momentum",
          total_return_pct: -1.0,
          annual_return_pct: 0,
          sharpe_ratio: -0.4,
          max_drawdown_pct: -2,
          win_rate: 40,
          final_value: 990_000,
          trade_count: 0,
          rank: 2,
        },
      ],
    },
  };
}

function singleAgentAnalysis(): ResultAnalysis {
  return {
    status: "done",
    start_date: "2024-03-14",
    end_date: "2024-03-15",
    trading_days: 2,
    config: {},
    benchmark: { name: "CSI 300", daily: [] },
    agents: { momentum: emptyAgent({ total_return_pct: -1.0 }, 990_000) },
    comparison: null,
  };
}

describe("Results", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.results.mockResolvedValue([]);
  });

  it("shows a ranked comparison overview before per-agent review for multi-agent runs", async () => {
    mockedApi.resultAnalysis.mockResolvedValue(multiAgentAnalysis());

    render(
      <MemoryRouter initialEntries={["/results?file=20260718_result.json"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText("横向排名");
    const rows = screen.getAllByRole("row").slice(1); // skip header row
    expect(rows[0]).toHaveTextContent("contrarian");
    expect(rows[1]).toHaveTextContent("momentum");
    expect(screen.getByText(/最佳/)).toHaveTextContent("contrarian");

    fireEvent.click(screen.getAllByRole("button", { name: /逐笔复盘/i })[0]);

    expect(screen.queryByText("横向排名")).not.toBeInTheDocument();
    expect(screen.getByText(/返回对比总览/)).toBeInTheDocument();
  });

  it("shows excess return vs the benchmark in the comparison ranking", async () => {
    const analysis = multiAgentAnalysis();
    analysis.benchmark.daily = [
      { date: "2024-03-14", equity: 1_000_000, daily_return_pct: 0, drawdown_pct: 0 },
      { date: "2024-03-15", equity: 1_020_000, daily_return_pct: 2, drawdown_pct: 0 },
    ];
    mockedApi.resultAnalysis.mockResolvedValue(analysis);

    render(
      <MemoryRouter initialEntries={["/results?file=20260718_result.json"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText("横向排名");
    expect(screen.getByText(/相对 沪深 300/)).toBeInTheDocument();
    // contrarian: 4.0% - benchmark 2.0% = +2.00%; momentum: -1.0% - 2.0% = -3.00%
    expect(screen.getByText("+2.00%")).toBeInTheDocument();
    expect(screen.getByText("-3.00%")).toBeInTheDocument();
  });

  it("never prefetches the raw artifact; export is a direct download link", async () => {
    mockedApi.resultAnalysis.mockResolvedValue(singleAgentAnalysis());

    render(
      <MemoryRouter initialEntries={["/results?file=20260718_result.json"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText(/momentum/);
    // The raw document (potentially tens of MB) must not be fetched on open.
    expect(mockedApi.result).not.toHaveBeenCalled();
    const exportLink = screen.getByRole("link", { name: /导出完整工件/ });
    expect(exportLink).toHaveAttribute("href", "/api/results/20260718_result.json");
    expect(exportLink).toHaveAttribute("download", "20260718_result.json");
  });

  it("skips the comparison overview for single-agent runs", async () => {
    mockedApi.resultAnalysis.mockResolvedValue(singleAgentAnalysis());

    render(
      <MemoryRouter initialEntries={["/results?file=20260718_result.json"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText(/momentum/);
    expect(screen.queryByText("横向排名")).not.toBeInTheDocument();
    expect(screen.queryByText(/返回对比总览/)).not.toBeInTheDocument();
  });

  it("deletes a result artifact after confirmation and removes it from the list", async () => {
    mockedApi.results.mockResolvedValue([
      { file: "a_result.json", status: "done", start_date: "2024-03-14", end_date: "2024-03-15", trading_days: 2, metrics: { total_return_pct: 1.5 } },
      { file: "b_result.json", status: "done", start_date: "2024-04-01", end_date: "2024-04-03", trading_days: 3, metrics: { total_return_pct: -2 } },
    ]);
    mockedApi.deleteResult.mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={["/results"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText(/a_result.json|2024\/03\/14/);
    fireEvent.click(screen.getByRole("button", { name: "删除结果工件 a_result.json" }));
    // Nothing is deleted until the dialog is confirmed.
    expect(mockedApi.deleteResult).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("a_result.json");

    fireEvent.click(screen.getByRole("button", { name: /确认删除/ }));
    await screen.findByText(/2024\/04\/01/);
    expect(mockedApi.deleteResult).toHaveBeenCalledWith("a_result.json");
    expect(screen.queryByText(/2024\/03\/14/)).not.toBeInTheDocument();
  });

  it("filters and sorts the library", async () => {
    mockedApi.results.mockResolvedValue([
      // Older artifact, later backtest window — must not win "最新优先".
      {
        file: "20260522_064848_result.json",
        status: "done",
        start_date: "2025-05-01",
        end_date: "2025-05-31",
        trading_days: 18,
        metrics: { total_return_pct: 4.53 },
      },
      // Newer artifact, earlier backtest window (demo).
      {
        file: "20260719_000202_result.json",
        status: "done",
        start_date: "2024-03-14",
        end_date: "2024-03-14",
        trading_days: 1,
        metrics: { total_return_pct: 0 },
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/results"]}>
        <Results />
      </MemoryRouter>,
    );

    // Default sort is newest recorded artifact first (filename timestamp).
    let cards = await screen.findAllByRole("button", { name: /202[45]\// });
    expect(cards[0]).toHaveTextContent("2024/03/14");
    expect(cards[1]).toHaveTextContent("2025/05/01");

    fireEvent.change(screen.getByLabelText("结果排序方式"), { target: { value: "return" } });
    cards = screen.getAllByRole("button", { name: /202[45]\// });
    expect(cards[0]).toHaveTextContent("2025/05/01");
    expect(cards[1]).toHaveTextContent("2024/03/14");

    fireEvent.change(screen.getByLabelText("筛选结果工件"), { target: { value: "20260719" } });
    expect(screen.queryByText(/2025\/05\/01/)).not.toBeInTheDocument();
    expect(screen.getByText(/2024\/03\/14/)).toBeInTheDocument();
  });

  it("compares two selected artifacts in an overlay view", async () => {
    mockedApi.results.mockResolvedValue([
      { file: "a_result.json", status: "done", start_date: "2024-03-14", end_date: "2024-03-15", trading_days: 2, metrics: { total_return_pct: 1.5 } },
      { file: "b_result.json", status: "done", start_date: "2024-04-01", end_date: "2024-04-03", trading_days: 3, metrics: { total_return_pct: 4 } },
    ]);
    mockedApi.resultAnalysis.mockImplementation((file: string) =>
      Promise.resolve(
        file === "a_result.json"
          ? singleAgentAnalysis()
          : {
              ...singleAgentAnalysis(),
              start_date: "2024-04-01",
              end_date: "2024-04-03",
              trading_days: 3,
            },
      ),
    );

    render(
      <MemoryRouter initialEntries={["/results"]}>
        <Results />
      </MemoryRouter>,
    );

    await screen.findByText(/2024\/03\/14/);
    fireEvent.click(screen.getByLabelText("选择 a_result.json 用于对比"));
    fireEvent.click(screen.getByLabelText("选择 b_result.json 用于对比"));
    fireEvent.click(screen.getByRole("button", { name: /对比所选 \(2\)/ }));

    expect(await screen.findByText("关键指标对比")).toBeInTheDocument();
    expect(screen.getByText("跨回测权益曲线叠加")).toBeInTheDocument();
    expect(mockedApi.resultAnalysis).toHaveBeenCalledWith("a_result.json");
    expect(mockedApi.resultAnalysis).toHaveBeenCalledWith("b_result.json");

    fireEvent.click(screen.getByRole("button", { name: /返回资料库/ }));
    expect(screen.queryByText("关键指标对比")).not.toBeInTheDocument();
  });
});
