import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EquityChart } from "./EquityChart";

describe("EquityChart", () => {
  it("renders agent and benchmark series with an accessible chart", () => {
    const { container } = render(
      <EquityChart
        series={[
          { label: "Agent", color: "#48d597", values: [["D+0", 100], ["D+1", 104]] },
          { label: "CSI 300", color: "#778191", values: [["D+0", 100], ["D+1", 101]] },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: /账户权益曲线/i })).toBeInTheDocument();
    expect(screen.getByText("CSI 300")).toBeInTheDocument();
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
  });

  it("aligns all series on a shared date axis so shorter series do not stretch", () => {
    const { container } = render(
      <EquityChart
        series={[
          { label: "Agent", color: "#48d597", values: [["D+0", 100], ["D+1", 104], ["D+2", 108]] },
          // Benchmark missing the last day: its final point must sit at the
          // middle of the axis, not be stretched to the right edge.
          { label: "CSI 300", color: "#778191", values: [["D+0", 100], ["D+1", 101]] },
        ]}
      />,
    );
    const benchmark = container.querySelectorAll("polyline")[1];
    const lastPoint = benchmark.getAttribute("points")!.split(" ").at(-1)!;
    // Plot area starts after the Y-axis gutter (64px) and spans 920px, so the
    // middle of three dates sits at 64 + 920 / 2 = 524.
    expect(Number(lastPoint.split(",")[0])).toBeCloseTo(524, 0);
  });

  it("shows a per-date readout that follows the hover position", () => {
    const { container } = render(
      <EquityChart
        series={[
          { label: "Agent", color: "#48d597", values: [["2024-03-04", 100], ["2024-03-05", 104]] },
        ]}
      />,
    );
    const readout = container.querySelector(".equity-readout")!;
    // Default readout is the latest date.
    expect(readout).toHaveTextContent("2024/03/05");
    const svg = screen.getByRole("img", { name: /账户权益曲线/i });
    svg.getBoundingClientRect = () =>
      ({ left: 0, width: 1000, top: 0, height: 300 }) as DOMRect;
    fireEvent.mouseMove(svg, { clientX: 10 });
    expect(readout).toHaveTextContent("2024/03/04");
    expect(container.querySelector(".chart-crosshair")).toBeInTheDocument();
  });

  it("renders Y-axis tick labels and an area fill under the primary series", () => {
    const { container } = render(
      <EquityChart
        series={[
          {
            label: "Agent",
            color: "#48d597",
            values: [["2024-03-04", 1_000_000], ["2024-03-05", 1_040_000]],
          },
        ]}
      />,
    );
    const ticks = container.querySelectorAll(".chart-tick");
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    // The area fill references a gradient defined inside the same svg.
    const fill = container.querySelector('path[fill^="url(#"]');
    expect(fill).toBeInTheDocument();
  });

  it("plots buy and sell markers on the primary series", () => {
    const { container } = render(
      <EquityChart
        series={[
          {
            label: "Agent",
            color: "#48d597",
            values: [["2024-03-04", 100], ["2024-03-05", 104], ["2024-03-06", 102]],
          },
        ]}
        markers={[
          { date: "2024-03-04", side: "buy" },
          { date: "2024-03-06", side: "sell" },
          // Dates outside the series are ignored.
          { date: "2024-03-09", side: "buy" },
        ]}
      />,
    );
    expect(container.querySelectorAll(".trade-marker.buy")).toHaveLength(1);
    expect(container.querySelectorAll(".trade-marker.sell")).toHaveLength(1);
  });
});
