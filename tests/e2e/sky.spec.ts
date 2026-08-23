import type { Page } from "@playwright/test";

import { expect, test } from "../../web/playwright";

// The fixture archive is centred on this instant.
const ANCHOR = "2026-08-20T15:03:17Z";
const serverFailures = new WeakMap<Page, string[]>();

test.describe("sky interface", () => {
  test.beforeEach(async ({ page }) => {
    const failures: string[] = [];
    serverFailures.set(page, failures);
    page.on("response", (response) => {
      if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
    });
    page.on("pageerror", (error) => failures.push(`pageerror ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error" && /\b5\d\d\b/.test(message.text())) {
        failures.push(`console ${message.text()}`);
      }
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Sky" }).click();
    await expect(page.getByLabel("Sky interface")).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    await page.waitForLoadState("networkidle");
    expect(serverFailures.get(page) ?? []).toEqual([]);
  });

  test("names the element set it drew from", async ({ page }) => {
    const provenance = page.getByLabel("Element set provenance");
    await expect(provenance).toContainText("TLE record used for this view");
    await expect(provenance).toContainText(/Space-Track|Hugging Face/);
    await expect(provenance).toContainText("sha256:");
  });

  test("lists local TLE snapshots with update time, coverage and source", async ({ page }) => {
    await page.getByRole("button", { name: "TLE" }).click();
    await expect(page.getByRole("main", { name: "TLE archive" })).toBeVisible();
    const table = page.getByLabel("Local TLE snapshots");
    await expect(table).toBeVisible();
    await expect(table.locator("tbody tr")).toHaveCount(6);
    await expect(table.locator("tbody tr").first()).toContainText("8");
    await expect(table).toContainText("Space-Track");
    await expect(table).toContainText("Hugging Face");
  });

  test("draws the globe and reports how many objects it holds", async ({ page }) => {
    await expect(page.getByLabel("Orbital globe")).toBeVisible();
    await expect(page.getByLabel("Rendered object count")).toContainText("objects");
    await expect(
      page.getByText(/Not a detection, attribution or identification/).first(),
    ).toBeVisible();
  });

  test("looks up from a reviewed site and charts the sky", async ({ page }) => {
    const anchor = page.getByLabel("Anchor instant");
    await anchor.fill(ANCHOR);
    await anchor.blur();

    await page.getByLabel("Reviewed observer site").selectOption("spinnaker-sausalito");
    await expect(page.getByLabel("All-sky chart")).toBeVisible();
    await expect(page.getByLabel("Observer position")).toContainText("Spinnaker");
    const table = page.getByLabel("Visible objects");
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /CH1 center · 10\.825 GHz/ })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /CH8 center · 12\.575 GHz/ })).toBeVisible();
  });

  test("compares five unique TLE records for a selected satellite", async ({ page }) => {
    const anchor = page.getByLabel("Anchor instant");
    await anchor.fill(ANCHOR);
    await anchor.blur();
    await page.getByLabel("Observer latitude").fill("0");
    await page.getByLabel("Observer longitude").fill("0");
    await page.getByRole("button", { name: "Look up from here" }).click();
    const table = page.getByLabel("Visible objects");
    await table.locator("tbody tr").first().getByRole("button").click();

    const comparison = page.getByLabel("Satellite TLE position comparison");
    await expect(comparison).toBeVisible();
    await expect(page.getByLabel("Latest satellite TLE entries").locator("tbody tr")).toHaveCount(5);
    await expect(comparison).toContainText("Used by view");
    await expect(comparison).toContainText("Δ 3D position");
  });

  test("looks up from a typed position", async ({ page }) => {
    const anchor = page.getByLabel("Anchor instant");
    await anchor.fill(ANCHOR);
    await anchor.blur();
    await page.getByLabel("Observer latitude").fill("0");
    await page.getByLabel("Observer longitude").fill("0");
    await page.getByRole("button", { name: "Look up from here" }).click();
    await expect(page.getByLabel("All-sky chart")).toBeVisible();
    const firstRow = page.getByLabel("Visible objects").locator("tbody tr").first();
    await expect(firstRow.locator("td").nth(4)).toContainText("Hz/s");
    await expect(firstRow.locator("td").nth(5)).toContainText("Hz/s");
  });

  test("refuses a position outside the globe", async ({ page }) => {
    await page.getByLabel("Observer latitude").fill("91");
    await page.getByLabel("Observer longitude").fill("0");
    await page.getByRole("button", { name: "Look up from here" }).click();
    await expect(page.getByText(/Latitude must be between/)).toBeVisible();
  });

  test("moves the displayed instant with the 120 second slider", async ({ page }) => {
    const anchor = page.getByLabel("Anchor instant");
    await anchor.fill(ANCHOR);
    await anchor.blur();

    const readout = page.getByLabel("Displayed instant");
    await expect(readout).toContainText("15:03:17");

    const slider = page.getByLabel("Time offset in seconds");
    await expect(slider).toHaveAttribute("min", "-60");
    await expect(slider).toHaveAttribute("max", "60");
    await slider.fill("60");
    await expect(readout).toContainText("15:04:17");
    await slider.fill("-60");
    await expect(readout).toContainText("15:02:17");
  });

  test("keeps the existing views reachable", async ({ page }) => {
    await page.getByRole("button", { name: "Recordings" }).click();
    await expect(page.getByRole("button", { name: "Sky" })).toBeVisible();
  });
});
