import { expect, test } from "../../web/playwright";

test("production dashboard reads an atomically promoted Standard TEST run", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Observation Console" })).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();
  await expect(page.getByText(/\d+% used/)).toBeVisible();

  const search = page.getByRole("searchbox", { name: "Search recordings" });
  await search.fill("e2e-main-test-recording");
  const row = page.getByRole("button", { name: /e2e-main-test-recording/ });
  await expect(row).toBeVisible();
  await expect(row).toContainText("TEST");
  await expect(row).toContainText("partial");
  await expect(row).toContainText("HELD");
  await row.click();

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

  await expect(page.getByText("Acquisition geometry")).toBeVisible();
  await expect(page.getByText("Power & quality")).toHaveCount(0);
  await expect(page.getByText("Synchronized stream waterfalls")).toHaveCount(0);
  await expect(page.getByText("Whole-dwell candidate evidence")).toHaveCount(0);
  await expect(page.getByLabel("Power timeline")).toHaveCount(0);
  await expect(page.getByLabel("Candidate overlay plot")).toHaveCount(0);

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
  await page.getByRole("button", { name: /e2e-failed-test-recording/ }).click();

  await expect(page.getByRole("heading", { name: "Production E2E intentional analysis failure" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("failed");
  await expect(page.getByText("Intentional production E2E analysis failure").first()).toBeVisible();
  await expect(page.getByText("No current run")).toBeVisible();
  await expect(page.getByText("Acquisition geometry")).toBeVisible();
  await expect(page.getByText("Power product unavailable")).toHaveCount(0);
  await expect(page.getByText("No waterfall product for this run.")).toHaveCount(0);
});
