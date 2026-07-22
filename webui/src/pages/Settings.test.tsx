import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { LLMConfig } from "../types";
import { Settings } from "./Settings";

vi.mock("../api", () => ({
  api: {
    getLLMConfig: vi.fn(),
    saveLLMConfig: vi.fn(),
    testLLMConfig: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const CONFIGURED: LLMConfig = {
  configured: true,
  source: "settings",
  api_key_masked: "sk-...dUWD",
  base_url: "https://api.deepseek.com",
  base_url_source: "default",
};

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.getLLMConfig.mockResolvedValue(CONFIGURED);
  });

  it("loads and displays the configured credential status", async () => {
    render(<Settings />);

    await screen.findByText("已配置");
    expect(screen.getByText("页面设置")).toBeInTheDocument();
    expect(screen.getByText("sk-...dUWD")).toBeInTheDocument();
    expect(screen.getByText("https://api.deepseek.com")).toBeInTheDocument();
    expect(screen.getByText("内置默认")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/sk-\.\.\.dUWD/)).toBeInTheDocument();
  });

  it("saves exactly the fields the user typed", async () => {
    mockedApi.saveLLMConfig.mockResolvedValue(CONFIGURED);
    render(<Settings />);
    await screen.findByText("已配置");

    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "sk-newsecret" } });
    fireEvent.change(screen.getByLabelText("请求地址 Base URL"), {
      target: { value: "https://proxy.example.com/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /保存设置/ }));

    await waitFor(() =>
      expect(mockedApi.saveLLMConfig).toHaveBeenCalledWith({
        api_key: "sk-newsecret",
        base_url: "https://proxy.example.com/v1",
      }),
    );
  });

  it("tests the connection and shows the successful result", async () => {
    mockedApi.testLLMConfig.mockResolvedValue({
      ok: true,
      detail: "连接成功",
      model: "deepseek-chat",
    });
    render(<Settings />);
    await screen.findByText("已配置");

    fireEvent.click(screen.getByRole("button", { name: /测试连接/ }));

    await screen.findByText(/连接成功 · 模型 deepseek-chat · 耗时/);
    expect(mockedApi.testLLMConfig).toHaveBeenCalledWith({ model: "deepseek-chat" });
  });

  it("shows the failure detail when the connection test fails", async () => {
    mockedApi.testLLMConfig.mockResolvedValue({
      ok: false,
      detail: "401 Unauthorized",
      model: "deepseek-chat",
    });
    render(<Settings />);
    await screen.findByText("已配置");

    fireEvent.click(screen.getByRole("button", { name: /测试连接/ }));

    await screen.findByText(/连接失败 · 模型 deepseek-chat · 401 Unauthorized/);
  });
});
