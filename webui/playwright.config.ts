import { defineConfig, devices } from "@playwright/test";

const python = process.env.CI
  ? "python"
  : process.platform === "win32"
    ? ".\\.venv\\Scripts\\python.exe"
    : "./.venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8766",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], channel: "chrome" } },
  ],
  webServer: {
    command: `${python} -m uvicorn traderharness.server.app:create_app --factory --host 127.0.0.1 --port 8766`,
    cwd: "..",
    url: "http://127.0.0.1:8766/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
