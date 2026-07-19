// Captures the frames used to rebuild docs/assets/traderharness-demo.gif plus a
// few full-page product screenshots referenced from the README. The console
// UI is entirely in Chinese (see src/locale.ts and src/components/Shell.tsx),
// so every selector below must match the real rendered Chinese copy rather
// than an English placeholder.
//
// Usage: from webui/, run `npm run capture:demo` against a running
// `traderharness ui` server (defaults to http://127.0.0.1:8766).
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const output = path.resolve("../docs/assets/demo-frames");
const assets = path.resolve("../docs/assets");
const baseUrl = process.env.TRADERHARNESS_DEMO_URL ?? "http://127.0.0.1:8766";
await mkdir(output, { recursive: true });
await mkdir(assets, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

// 1. 工作台首页 — the operator lands here and can launch the no-key replay.
await page.goto(baseUrl);
const demoButton = page.getByRole("button", { name: "运行免密演示" });
await demoButton.waitFor();
await page.screenshot({ path: path.join(output, "01-dashboard.png") });

// 2. 回测控制室 — streaming, still running. The dashboard's "运行免密演示"
// button starts the bundled masked replay and navigates to /live.
await demoButton.click();
await page.getByRole("heading", { name: "回测控制室", level: 1 }).waitFor();
await page.locator(".office-floor").waitFor();
await page.waitForTimeout(1_200);
await page.screenshot({ path: path.join(output, "02-live.png") });
await page.screenshot({ path: path.join(assets, "live-control-room.png"), fullPage: true });

// 3. 结果资料库 — once the run finishes, the console hops straight to the
// completed run's dossier (no manual "回测结果" click needed). It lands on
// the "逐笔复盘" tab by default.
await page.waitForURL(/\/results\?file=/, { timeout: 90_000 });
await page.getByRole("heading", { name: "回测研究档案", level: 1 }).waitFor();
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(output, "03-complete.png") });

// 4. 绩效总览 — equity curve versus the CSI 300 benchmark, drawdown, and
// tool-usage evidence for the same run.
const overviewTab = page.locator(".dossier-tabs button", { hasText: "绩效总览" });
await overviewTab.waitFor({ timeout: 60_000 });
await overviewTab.click();
await page.getByRole("heading", { name: "权益曲线与基准对比", level: 2 }).waitFor();
await page.screenshot({ path: path.join(output, "04-results.png") });
await page.screenshot({ path: path.join(assets, "results-workbench.png"), fullPage: true });

// 5. 逐笔复盘 — per-trade K-line context, the agent's reasoning, and the
// exact tool call that produced the fill.
await page.locator(".dossier-tabs button", { hasText: "逐笔复盘" }).click();
await page.locator("h3", { hasText: "成交时 K 线" }).or(page.getByText(/没有可复盘|No completed|尚无/)).first().waitFor();
await page.screenshot({ path: path.join(output, "05-securities.png") });

// 6. 完整决策轨迹 — the full per-day decision timeline.
await page.locator(".dossier-tabs button", { hasText: "完整决策轨迹" }).click();
await page.waitForTimeout(500);
await page.screenshot({ path: path.join(output, "06-decisions.png") });

// 7. 智能体对比 — independent-portfolio race workbench.
await page.getByRole("link", { name: "智能体对比", exact: true }).click();
await page.getByRole("heading", { name: "智能体横向对比", level: 1 }).waitFor();
await page.screenshot({ path: path.join(assets, "compare-workbench.png"), fullPage: true });

await browser.close();
