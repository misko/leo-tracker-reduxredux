// Read-only browser check: never activate capture controls on the target app.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const [baseUrl, stylesheet] = process.argv.slice(2);
assert(baseUrl, "Supply the application URL; optionally supply a candidate stylesheet.");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Stop capture", exact: true }).waitFor();
  if (stylesheet) await page.addStyleTag({ path: stylesheet });
  const checks = [];
  for (const width of [1920, 1600, 1500, 1280, 1100, 900, 760, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const name of ["Start capture", "Stop capture", "Native refinement"]) {
      const button = page.getByRole("button", { name, exact: true });
      // Small screens intentionally scroll the navigation strip; capture
      // controls must fit without scrolling or activating either control.
      if (name === "Native refinement") await button.scrollIntoViewIfNeeded();
      const box = await button.boundingBox();
      assert(box && box.width > 0 && box.height > 0, `${width}: ${name} has no box`);
      assert(box.x >= 0 && box.x + box.width <= width, `${width}: ${name} is clipped horizontally`);
      assert(box.y >= 0 && box.y + box.height <= 1000, `${width}: ${name} is clipped vertically`);
    }
    checks.push({ width, controls_and_native_navigation_in_view: true });
  }
  console.log(JSON.stringify({ base_url: baseUrl, candidate_stylesheet: stylesheet ?? null, checks, capture_controls_activated: false }, null, 2));
} finally {
  await browser.close();
}
