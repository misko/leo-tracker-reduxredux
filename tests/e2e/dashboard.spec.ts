import { expect, test } from "../../web/playwright";

test("production dashboard reads an atomically promoted Standard TEST run", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Observation Console" })).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();
  await expect(page.getByText(/\d+% used/)).toBeVisible();

  const search = page.getByRole("searchbox", { name: "Search recordings" });
  await search.fill("e2e-main-test-recording");
  const row = page.getByRole("button", { name: /Production E2E paired TEST dwell/ });
  await expect(row).toBeVisible();
  await expect(row).toContainText("TEST");
  await expect(row).toContainText("partial");
  await expect(row).toContainText("HELD");
  await page.getByRole("button", { name: /Production E2E paired TEST dwell/ }).click();

  await expect(page.getByRole("heading", { name: "Production E2E paired TEST dwell" })).toBeVisible();
  await expect(page.getByText("Held · automatic TEST corpus hold")).toBeVisible();
  await expect(page.getByText("e2e-main-run-v2", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("e2e-main-run-v1", { exact: true })).toHaveCount(0);

  await expect(page.getByText("best effort · observed")).toBeVisible();
  await expect(page.getByText("0.0007692 s", { exact: true })).toBeVisible();
  await expect(page.getByText("phase coherent: no")).toBeVisible();
  await expect(page.getByText(/bulk\/recordings\/2026\/05\/28\/e2e-main-test-recording$/)).toBeVisible();
  await expect(page.getByText(/bulk\/analysis\/e2e-main-test-recording\/e2e-main-run-v2$/)).toBeVisible();
  await expect(page.getByText(/waterfall · ap-/).first()).toBeVisible();

  await expect(page.getByLabel("Power timeline")).toBeVisible();
  await expect(page.getByLabel("Waterfall stream-1")).toContainText("e2e-radio-a");
  await expect(page.getByLabel("Waterfall stream-2")).toContainText("e2e-radio-b");
  await expect(page.getByLabel("Waterfall plot")).toHaveCount(2);
  await expect(page.getByText("192 / 512 display points")).toHaveCount(2);
  await expect(page.getByLabel("Candidate overlay plot")).toHaveCount(2);
  await expect(page.getByText(/0 bounded candidate overlays · run e2e-main-run-v2/)).toHaveCount(2);

  await expect(page.getByLabel("Analysis stream-1")).toContainText("e2e-radio-a");
  await expect(page.getByLabel("Analysis stream-2")).toContainText("e2e-radio-b");
  await expect(page.getByRole("heading", { name: "Whole-dwell candidate evidence" })).toHaveCount(2);
  await expect(page.getByText("standard", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("insufficient", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("0 / 0 complete")).toHaveCount(2);
  await expect(page.getByText("verified")).toHaveCount(2);
  await expect(page.getByText("No candidate", { exact: true })).toHaveCount(2);
  await expect(page.locator("strong.evidence-value", { hasText: "No result" }).first()).toBeVisible();
  await expect(page.getByText("No track", { exact: true })).toHaveCount(2);
  await expect(page.getByLabel("Analysis stream-1").getByText(/^TLE:/)).toBeVisible();
  await expect(page.getByLabel("Analysis stream-2").getByText(/^TLE:/)).toBeVisible();

  const mutationStatuses = await page.evaluate(async () => {
    const paths = [
      "/api/v1/recordings",
      "/api/v1/recordings/e2e-main-test-recording",
      "/api/v1/status",
    ];
    return Promise.all(paths.map(async (path) => (await fetch(path, { method: "POST" })).status));
  });
  expect(mutationStatuses).toEqual([405, 405, 405]);
  await expect(page.getByRole("button", { name: /^(start capture|purge|reprocess)$/i })).toHaveCount(0);
});

test("production dashboard exposes an ordinary failed analysis explicitly", async ({ page }) => {
  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "Search recordings" });
  await search.fill("e2e-failed-test-recording");
  await page.getByRole("button", { name: /Production E2E intentional analysis failure/ }).click();

  await expect(page.getByRole("heading", { name: "Production E2E intentional analysis failure" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("failed");
  await expect(page.getByText("Intentional production E2E analysis failure").first()).toBeVisible();
  await expect(page.getByText("No current run")).toBeVisible();
  await expect(page.getByText("Power product unavailable")).toBeVisible();
  await expect(page.getByText("No waterfall product for this run.")).toBeVisible();
});
