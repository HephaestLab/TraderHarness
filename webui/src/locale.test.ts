import { describe, expect, it } from "vitest";
import {
  agentDisplayName,
  formatDate,
  phaseLabel,
  riskLabel,
  sideLabel,
  statusLabel,
  strategyTagLabel,
  toolLabel,
  windowLabel,
} from "./locale";

describe("中文界面映射", () => {
  it("翻译动态状态但保留工具技术标识", () => {
    expect(statusLabel("running")).toBe("运行中");
    expect(phaseLabel("close_window")).toBe("尾盘阶段");
    expect(windowLabel("open_1")).toBe("开盘窗口 1");
    expect(sideLabel("buy")).toBe("买入");
    expect(riskLabel("conservative")).toBe("保守");
    expect(toolLabel("place_order")).toBe("下单（place_order）");
  });

  it("中文化日期、策略标签和内置 Agent 名称", () => {
    expect(formatDate("2024-03-14")).toBe("2024/03/14");
    expect(formatDate("D-1")).toBe("D-1");
    expect(strategyTagLabel("event-driven")).toBe("事件驱动");
    expect(agentDisplayName("trend-breakout", "Trend Breakout")).toBe("趋势突破者");
  });
});
