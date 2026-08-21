import { expect, test } from "../../web/playwright";

test("production dashboard reads an atomically promoted Standard import run", async ({ page }) => {
  const serverFailures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) serverFailures.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => serverFailures.push(`pageerror ${error.message}`));
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Observation Console" })).toBeVisible();
  await expect(page.getByText("Presentation only")).toBeVisible();
  await expect(page.getByText(/\d+% used/)).toBeVisible();

  const search = page.getByRole("searchbox", { name: "Search recordings" });
  await search.fill("e2e-main-test-recording");
  const row = page.getByRole("button", { name: /e2e-main-test-recording/ });
  await expect(row).toBeVisible();
  await expect(row).toContainText("IMPORT");
  await expect(row).toContainText("no result");
  await row.click();

  await expect(page.getByRole("heading", { name: "Production E2E paired imported dwell" })).toBeVisible();
  await expect(page.getByText("e2e-main-run-v2", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("e2e-main-run-v1", { exact: true })).toHaveCount(0);

  await expect(page.getByText("best effort · observed")).toBeVisible();
  await expect(page.getByText("0.0007692 s", { exact: true })).toBeVisible();
  await expect(page.getByText("phase coherent: no")).toBeVisible();
  await expect(page.getByText(/bulk\/recordings\/2026\/05\/28\/e2e-main-test-recording$/)).toBeVisible();
  await expect(page.getByText(/bulk\/analysis\/e2e-main-test-recording\/e2e-main-run-v2$/)).toBeVisible();
  await expect(page.getByText(/quality · ap-/).first()).toBeVisible();

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

  const pairedHough = page.getByRole("region", {
    name: "Paired receiver-path Hough CFO candidates",
  });
  await expect(pairedHough).toBeVisible();
  await expect(pairedHough.getByRole("img")).toHaveCount(4);
  for (const label of ["Radio0 RX0", "Radio0 RX1", "Radio1 RX0", "Radio1 RX1"]) {
    const image = pairedHough.getByRole("img", { name: `Alternate Hough CFO candidates for ${label}` });
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((element: HTMLImageElement) => ({
      complete: element.complete,
      naturalWidth: element.naturalWidth,
    }))).toEqual({ complete: true, naturalWidth: expect.any(Number) });
    expect(await image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
  }
  await expect(pairedHough).toContainText("No joint or cross-radio Hough product is inferred");
  await page.waitForLoadState("networkidle");
  expect(serverFailures).toEqual([]);
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

test("an in-progress recording reports pending Standard images without a server outage", async ({ page }) => {
  const serverFailures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) serverFailures.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => serverFailures.push(`pageerror ${error.message}`));

  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "Search recordings" });
  await search.fill("e2e-pending-test-recording");
  await page.getByRole("button", { name: /e2e-pending-test-recording/ }).click();

  await expect(page.getByRole("status")).toContainText(/queued|in progress/);
  await expect(page.getByRole("alert")).toContainText(
    "Standard analysis is still processing; no sealed image artifacts are available yet",
  );
  await page.waitForLoadState("networkidle");
  expect(serverFailures).toEqual([]);
});

test("scanner view renders the latest bounded report without a network failure", async ({ page }) => {
  const serverFailures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) serverFailures.push(`${response.status()} ${response.url()}`);
  });
  page.on("pageerror", (error) => serverFailures.push(`pageerror ${error.message}`));

  await page.goto("/");
  await page.getByRole("button", { name: "Scanner" }).click();

  await expect(page.getByRole("heading", { name: "Latest Starlink channel scan" })).toBeVisible();
  await expect(page.getByText("6/8 active")).toBeVisible();
  await expect(page.getByText("scan-e2e-latest")).toBeVisible();
  await expect(page.getByRole("table", { name: "Latest scanner results" })).toContainText("CH4");
  await expect(page.getByText("Candidate-only GLRT64; no payload decoded")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(serverFailures).toEqual([]);
});
