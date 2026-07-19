// Captures the frames used to rebuild docs/assets/traderharness-demo.gif plus
// the full set of product screenshots referenced from the README. The console
// UI is entirely in Chinese (see src/locale.ts and src/components/Shell.tsx),
// so every selector below must match the real rendered Chinese copy rather
// than an English placeholder.
//
// Console 2.0 flow notes (why this script looks different from the old one):
// - The live run no longer auto-redirects when it finishes; a "查看研究档案 →"
//   button appears instead and the script must click it.
// - /results gained a library with checkable cards (2–4) feeding the cross-run
//   comparison view, and the dossier has four tabs (逐笔复盘 / 绩效总览 /
//   完整决策轨迹 / 成交台账).
// - Multi-agent runs open the dossier on the 对比总览 (ranking) view.
//
// Usage: from webui/, run `npm run capture:demo` against a running
// `traderharness ui` server (defaults to http://127.0.0.1:8766, override with
// TRADERHARNESS_DEMO_URL).
//
// Capture-window knobs (for long showcase runs):
// - CAPTURE_WARMUP_DAYS: trading days to let accumulate before the mid-run
//   stills (default 5).
// - CAPTURE_DONE_TIMEOUT_MS: max wait for the run to finish (default 25 min).
import { chromium } from "@playwright/test";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const output = path.resolve("../docs/assets/demo-frames");
const assets = path.resolve("../docs/assets");
const takes = path.join(output, "office-takes");
const baseUrl = process.env.TRADERHARNESS_DEMO_URL ?? "http://127.0.0.1:8766";
const warmupDays = Number(process.env.CAPTURE_WARMUP_DAYS ?? 5);
const doneTimeoutMs = Number(process.env.CAPTURE_DONE_TIMEOUT_MS ?? 1_500_000);

// Rich historical single-agent artifacts kept as alternates for the dossier
// stills (the two runs share the same 2024-03 window, so their equity curves
// overlay cleanly in the cross-run comparison).
const ALT_REVIEW_FILE = "20260717_122755_result.json"; // 20 天 · 27 笔成交
const ALT_OVERVIEW_FILE = "20260717_110738_result.json"; // 20 天 · 含沪深300基准

// CAPTURE_SKIP_RUN=1 reuses the most recent (already finished) run instead of
// launching a new demo — handy when the first pass reached the dossier stage
// and only the post-run stills need a retake.
const skipRun = process.env.CAPTURE_SKIP_RUN === "1";

await mkdir(output, { recursive: true });
await mkdir(assets, { recursive: true });
if (!skipRun) {
  // Start from a clean frame directory so the GIF never picks up stale frames.
  await rm(takes, { recursive: true, force: true });
  for (const file of await readdir(output)) {
    if (file.endsWith(".png")) await rm(path.join(output, file));
  }
}
await mkdir(takes, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});
page.setDefaultTimeout(60_000);

const frame = (name) => page.screenshot({ path: path.join(output, name) });
const asset = (name, opts = {}) =>
  page.screenshot({ path: path.join(assets, name), ...opts });

// 1. 工作台首页 — the operator lands here and can launch the no-key replay.
await page.goto(skipRun ? `${baseUrl}/live` : baseUrl);
if (!skipRun) {
  const demoButton = page.getByRole("button", { name: "运行免密演示" });
  await demoButton.waitFor();
  await page.waitForTimeout(600);
  await frame("01-dashboard.png");

  // 2. 回测控制室 — the dashboard button starts the bundled masked replay and
  // navigates to /live?run=<id>. While the run streams we harvest office
  // close-ups (bubble / walking moments) and the early GIF frames.
  await demoButton.click();
}
await page.getByRole("heading", { name: "回测控制室", level: 1 }).waitFor();
const office = page.locator(".office-floor");
await office.waitFor();
await page.waitForTimeout(1_200);

const dossierButton = page.getByRole("button", { name: /查看研究档案/ });
const failureNotice = page.getByText("回测失败：");
const progressFacts = page.locator(".lp-progress-facts strong");

async function daysDone() {
  const text = (await progressFacts.textContent().catch(() => "")) ?? "";
  const match = /第\s*(\d+)\s*\/\s*(\d+)\s*个交易日/.exec(text);
  return match ? Number(match[1]) : 0;
}

let take = (await readdir(takes)).filter((name) => /^take-\d+/.test(name)).length;
async function officeTake(tag) {
  take += 1;
  await office
    .screenshot({
      path: path.join(
        takes,
        `take-${String(take).padStart(3, "0")}${tag ? `-${tag}` : ""}.png`,
      ),
    })
    .catch(() => {});
}

// Element screenshots scroll the page; restore the top before viewport frames,
// and un-stick the topbar so fullPage stitches don't clip the page heading.
async function resetScroll({ desticky = false } = {}) {
  if (desticky) {
    await page.addStyleTag({ content: ".topbar{position:static!important}" }).catch(() => {});
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(250);
}

// Phase A: warm the run up so the ticker / wall graph / performance chart all
// hold real data before the mid-run stills.
const warmupStart = Date.now();
let warmed = false;
while (!warmed && Date.now() - warmupStart < 600_000) {
  await page.waitForTimeout(2_000);
  await officeTake();
  if (!skipRun && take === 5) {
    await resetScroll();
    await frame("02-live-early.png");
  }
  if (await failureNotice.isVisible().catch(() => false)) {
    throw new Error("演示运行失败，停止截图（请检查后端日志）。");
  }
  if (await dossierButton.isVisible().catch(() => false)) break; // short demo
  warmed = (await daysDone()) >= warmupDays;
}
if (!skipRun) {
  await resetScroll();
  await frame("03-live-mid.png");
}
await page
  .locator(".lp-panel")
  .screenshot({ path: path.join(takes, "live-performance-mid.png") });
await officeTake("warm");

// Phase B: keep the camera rolling at a slower cadence until the run ends.
let finished = await dossierButton.isVisible().catch(() => false);
const doneStart = Date.now();
while (!finished && Date.now() - doneStart < doneTimeoutMs) {
  await page.waitForTimeout(12_000);
  await officeTake();
  if (await failureNotice.isVisible().catch(() => false)) {
    throw new Error("演示运行失败，停止截图（请检查后端日志）。");
  }
  finished = await dossierButton.isVisible().catch(() => false);
}
if (!finished) throw new Error("等待演示运行结束超时。");

// 3. Run finished in place: ticker / Wall-Graph / performance panel now hold
// the final equity curves, and the header offers the dossier entry point.
await page.waitForTimeout(1_800);
await resetScroll();
await frame("04-live-done.png");
await resetScroll({ desticky: true });
await asset("live-control-room.png", { fullPage: true });
await page
  .locator(".lp-panel")
  .screenshot({ path: path.join(assets, "live-performance.png") });
await officeTake("done");
await writeFile(path.join(takes, "run-url.txt"), `demo run page: ${page.url()}\n`, "utf8");

// 4. 研究档案 — click through the new "查看研究档案 →" button. A multi-agent
// run opens on the 对比总览 ranking view (equity overlay + 横向排名).
await dossierButton.click();
await page.getByRole("heading", { name: "回测研究档案", level: 1 }).waitFor();
// The analysis dossier loads asynchronously (larger artifacts take seconds);
// wait for either the multi-agent ranking overview or the single-agent tabs.
const rankingTable = page.locator(".comparison-ranking");
await rankingTable
  .or(page.locator(".dossier-tabs"))
  .first()
  .waitFor({ timeout: 120_000 });
await page.waitForTimeout(800);
await resetScroll();
await frame("05-demo-dossier.png");
const isMultiAgent = await rankingTable.isVisible().catch(() => false);
if (isMultiAgent) {
  await page.getByRole("heading", { name: "多智能体权益曲线叠加", level: 2 }).waitFor();
  await page.waitForTimeout(600);
  await resetScroll();
  await frame("06-compare-overview.png");
  await resetScroll({ desticky: true });
  await asset("compare-workbench.png", { fullPage: true });
}
// Remember which result artifact this run produced (for the compare step).
const dossierUrl = new URL(page.url());
const demoResultFile = dossierUrl.searchParams.get("file") ?? "";
await writeFile(path.join(takes, "run-url.txt"), `demo result: ${demoResultFile}\n`, {
  encoding: "utf8",
  flag: "a",
});

// 5. 逐笔复盘 — enter the best agent's per-trade workbench from the ranking
// (or switch directly for single-agent dossiers).
if (isMultiAgent) {
  const reviewEntry = page
    .locator(".comparison-ranking button", { hasText: "逐笔复盘" })
    .first();
  await reviewEntry.waitFor();
  await reviewEntry.click();
  await page.locator(".dossier-tabs").waitFor();
} else {
  await page.locator(".dossier-tabs button", { hasText: "逐笔复盘" }).click();
}
const workbench = page.locator(".trade-review-workbench");
await workbench
  .or(page.getByText("没有可复盘的已成交订单"))
  .first()
  .waitFor();
await page.waitForTimeout(600);
await resetScroll();
await frame("07-trade-review.png");
if (await workbench.isVisible().catch(() => false)) {
  // Element close-up: hide the sticky topbar so stitching can't clip content.
  await page.addStyleTag({ content: ".topbar{display:none!important}" }).catch(() => {});
  await workbench.screenshot({ path: path.join(takes, "trade-review-live.png") });
}

// 6. 绩效总览 of the same run — new EquityChart (crosshair tooltip, Y ticks,
// buy/sell markers), drawdown, behavior fingerprint, tool usage.
const overviewTab = page.locator(".dossier-tabs button", { hasText: "绩效总览" });
await overviewTab.click();
await page.getByRole("heading", { name: "权益曲线与基准对比", level: 2 }).waitFor();
await page.locator(".behavior-panel").waitFor();
await page.waitForTimeout(600);
await resetScroll();
await frame("08-overview.png");
await resetScroll({ desticky: true });
await page.screenshot({ path: path.join(takes, "results-workbench-live.png"), fullPage: true });

// 7. Alternate dossier stills from the rich recorded single-agent artifacts,
// so the final assets can pick whichever tells the better story.
await page.goto(`${baseUrl}/results?file=${encodeURIComponent(ALT_REVIEW_FILE)}`);
await page.getByRole("heading", { name: "回测研究档案", level: 1 }).waitFor();
const altWorkbench = page.locator(".trade-review-workbench");
await altWorkbench.waitFor();
const sellTrades = page.locator(".fill-list button", { has: page.locator("b.side.sell") });
if ((await sellTrades.count()) > 1) await sellTrades.nth(1).click();
await page.waitForTimeout(500);
await page.addStyleTag({ content: ".topbar{display:none!important}" }).catch(() => {});
await altWorkbench.screenshot({ path: path.join(takes, "trade-review-alt.png") });

await page.goto(`${baseUrl}/results?file=${encodeURIComponent(ALT_OVERVIEW_FILE)}`);
await page.getByRole("heading", { name: "回测研究档案", level: 1 }).waitFor();
await page.locator(".dossier-tabs button", { hasText: "绩效总览" }).click();
await page.getByRole("heading", { name: "权益曲线与基准对比", level: 2 }).waitFor();
await page.locator(".behavior-panel").waitFor();
await page.waitForTimeout(600);
await resetScroll({ desticky: true });
await page.screenshot({ path: path.join(takes, "results-workbench-alt.png"), fullPage: true });

// 8. 结果资料库 — filter down to the demo artifact + the rich alternate, tick
// both cards, and enter the cross-run comparison view.
await page.goto(`${baseUrl}/results`);
await page.getByRole("heading", { name: "结果资料库", level: 1 }).waitFor();
await page.locator(".result-card").first().waitFor();
const compareFiles = [demoResultFile, ALT_OVERVIEW_FILE].filter(Boolean);
for (const file of compareFiles) {
  await page.getByRole("checkbox", { name: `选择 ${file} 用于对比` }).check();
}
await page.locator(".compare-selection-bar").waitFor();
await page.waitForTimeout(300);
await resetScroll();
await frame("09-library-select.png");
await page.getByRole("button", { name: /对比所选/ }).click();
await page.getByRole("heading", { name: "跨回测权益曲线叠加", level: 2 }).waitFor();
await page.waitForTimeout(600);
await resetScroll();
await frame("10-run-compare.png");
await resetScroll({ desticky: true });
await asset("run-compare.png", { fullPage: true });

// 9. Social-preview background — high-resolution capture of the finished live
// run (office + performance rail) for build_social_preview.py to crop.
const socialPage = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});
await socialPage.goto(`${baseUrl}/live`);
await socialPage.locator(".office-floor").waitFor();
await socialPage.waitForTimeout(3_000);
await socialPage
  .locator(".live-layout-v2")
  .screenshot({ path: path.join(takes, "social-bg.png") });

await browser.close();
console.log("capture complete:", { takes: take, demoResultFile, frames: await readdir(output) });
