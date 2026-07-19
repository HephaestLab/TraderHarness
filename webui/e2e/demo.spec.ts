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
  // LiveRun auto-navigates to the completed dossier when the run finishes.
  await page.waitForURL(/\/results\?file=/, { timeout: 90_000 });
  await expect(page.getByRole("heading", { name: "回测研究档案", level: 1 })).toBeVisible();
  await expect(page.locator(".dossier-tabs button", { hasText: "逐笔复盘" })).toBeVisible();

  await page.getByRole("link", { name: "回测结果" }).click();
  await expect(page.getByRole("heading", { name: "结果资料库" })).toBeVisible();
  await expect(page.getByRole("button", { name: /2024\/03\/14/ }).first()).toBeVisible();
});
