import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CandlestickChart } from "./CandlestickChart";

describe("CandlestickChart", () => {
  it("renders OHLC evidence and transaction markers", () => {
    render(
      <CandlestickChart
        bars={[
          { date: "2024-03-13", open: 10, high: 10.8, low: 9.8, close: 10.5, volume: 1200 },
          { date: "2024-03-14", open: 10.5, high: 10.7, low: 10.1, close: 10.2, volume: 900 },
        ]}
        markers={[
          { date: "2024-03-14", side: "buy", price: 10.3, quantity: 100, reasoning: "breakout", window: "open_1" },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: /K 线图/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/买入 100 股，价格 10.30/i)).toBeInTheDocument();
    expect(screen.getByText("2024/03/13")).toBeInTheDocument();
  });
});
