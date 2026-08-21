import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "../tests/e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:8766",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "cd .. && PYTHONPATH=src:. uv run --frozen --no-sync uvicorn server:app --app-dir tests/e2e --host 127.0.0.1 --port 8766",
    url: "http://127.0.0.1:8766/api/v1/status",
    reuseExistingServer: false,
    timeout: 90_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
  },
  projects: [
    {
      name: "production-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
