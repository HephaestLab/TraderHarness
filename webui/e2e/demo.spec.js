import { expect, test } from "@playwright/test";

test("工作台展示运行环境状态", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "智能体研究台" })).toBeVisible();
  await expect(page.getByText("市场数据").locator("..")).toBeVisible();
  await page.getByRole("link", { name: "智能体", exact: true }).click();
  await expect(page.getByRole("heading", { name: "交易研究团队" })).toBeVisible();
  await page.getByRole("link", { name: "智能体对比", exact: true }).click();
  await expect(page.getByRole("heading", { name: "智能体横向对比" })).toBeVisible();
  await page.getByRole("link", { name: "回测结果" }).click();
  await expect(page.getByRole("heading", { name: "结果资料库" })).toBeVisible();
});

test("免密演示可回放事件并保存结果", async ({ page }) => {
  test.skip(Boolean(process.env.CI), "full replay test requires the real local dataset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "智能体研究台" })).toBeVisible();
  await expect(page.getByText("市场数据").locator("..")).toContainText("就绪");

  await page.getByRole("button", { name: /运行免密演示/i }).click();
  await expect(page).toHaveURL(/\/live\?run=/);
  await expect(page.getByRole("heading", { name: "回测控制室" })).toBeVisible();
  await expect(page.getByText("决策事件流")).toBeVisible();
  // LiveRun no longer auto-navigates; once the run reaches a terminal state a
  // "查看研究档案 →" button appears and opens the completed dossier on demand.
  const openDossier = page.getByRole("button", { name: /查看研究档案/ });
  await expect(openDossier).toBeVisible({ timeout: 90_000 });
  await openDossier.click();
  await expect(page).toHaveURL(/\/results\?file=/);
  await expect(page.getByRole("heading", { name: "回测研究档案", level: 1 })).toBeVisible();
  await expect(page.locator(".dossier-tabs button", { hasText: "逐笔复盘" })).toBeVisible();

  await page.getByRole("link", { name: "回测结果" }).click();
  await expect(page.getByRole("heading", { name: "结果资料库" })).toBeVisible();
  await expect(page.getByRole("button", { name: /2024\/03\/14/ }).first()).toBeVisible();
});

test("one-click masking showcase works without credentials or a dataset action", async ({ page }) => {
  await page.goto("/showcase");
  await expect(page.getByRole("heading", { name: "Masked vs Unmasked" })).toBeVisible();
  await expect(page.getByText("Recorded experiment — not a live backtest")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Masked", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.locator(".showcase-config")).toContainText("Date masking ON");
  await expect(page.locator(".showcase-config")).toContainText("Entity masking ON");

  await page.getByRole("tab", { name: "Unmasked control" }).click();
  await expect(page.getByRole("tab", { name: "Unmasked control" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.locator(".showcase-config")).toContainText("Date masking OFF");
  await expect(page.locator(".showcase-config")).toContainText("Entity masking OFF");
});

test("one-click masking showcase remains usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/showcase");
  await expect(page.getByRole("heading", { name: "Masked vs Unmasked" })).toBeVisible();
  await page.getByRole("tab", { name: "Unmasked control" }).click();
  await expect(page.locator(".showcase-condition")).toBeVisible();
});

test("paper arena supports multi-agent selection and responsive audit navigation", async ({ page }) => {
  await page.goto("/paper");
  await expect(page.getByRole("heading", { name: "多 Agent 每日模拟盘" })).toBeVisible();
  await expect(page.getByText("市场播报台")).toBeVisible();
  await expect(page.getByRole("heading", { name: "可解释工作轨迹" })).toBeVisible();

  const candidates = page.locator(".arena-agent-options button");
  await expect(candidates.first()).toBeVisible();
  expect(await candidates.count()).toBeGreaterThanOrEqual(2);
  for (let index = 2; index < await candidates.count(); index += 1) {
    if (await candidates.nth(index).getAttribute("aria-pressed") === "true") {
      await candidates.nth(index).click();
    }
  }
  for (let index = 0; index < 2; index += 1) {
    if (await candidates.nth(index).getAttribute("aria-pressed") !== "true") {
      await candidates.nth(index).click();
    }
  }
  await expect(candidates.nth(0)).toHaveAttribute("aria-pressed", "true");
  await expect(candidates.nth(1)).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /启动 [2-4] 个 Agent/ })).toBeVisible();
  await page.getByRole("button", { name: /工具与代码/ }).click();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "多 Agent 每日模拟盘" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
