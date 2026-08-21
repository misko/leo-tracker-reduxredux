import { expect, test } from "../../web/playwright";

// The fixture archive is centred on this instant.
const ANCHOR = "2026-08-20T15:03:17Z";

test.describe("sky interface", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Sky" }).click();
    await expect(page.getByLabel("Sky interface")).toBeVisible();
  });

  test("names the element set it drew from", async ({ page }) => {
    const provenance = page.getByLabel("Element set provenance");
    await expect(provenance).toContainText("space-track");
    await expect(provenance).toContainText("sha256:");
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
    await expect(page.getByLabel("Visible objects")).toBeVisible();
  });

  test("looks up from a typed position", async ({ page }) => {
    await page.getByLabel("Observer latitude").fill("0");
    await page.getByLabel("Observer longitude").fill("0");
    await page.getByRole("button", { name: "Look up from here" }).click();
    await expect(page.getByLabel("All-sky chart")).toBeVisible();
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
