import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StructuredPayload } from "./StructuredPayload";

describe("StructuredPayload", () => {
  it("turns JSON-encoded tool output into readable fields", () => {
    render(<StructuredPayload title="工具返回" value={'{"stdout":"21","ok":true}'} />);
    expect(screen.getByText("stdout")).toBeInTheDocument();
    expect(screen.getByText("21")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
  });

  it("renders Python with line numbers and supports copying", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<StructuredPayload value={{ code: "x = 1\nprint(x)" }} />);
    expect(screen.getByLabelText("python 代码")).toHaveTextContent("print(x)");
    expect(screen.getByText("2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制代码" }));
    expect(writeText).toHaveBeenCalledWith("x = 1\nprint(x)");
  });
});
