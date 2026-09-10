// Read-only browser verification. Never presses a capture-control button.
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { join, isAbsolute } from "node:path";
const require = createRequire("/opt/leo-tracker/current-api/web/package.json");
const { chromium } = require("@playwright/test");
const [kind, session, output] = process.argv.slice(2);
if (!["fixed", "adaptive"].includes(kind) || !/^scan-hop-[a-f0-9]+$/.test(session)
    || !isAbsolute(output) || output.startsWith("/mnt/qnap01")) throw new Error("invalid inputs");
await mkdir(output, { recursive: false });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
const requests = [], errors = [], figures = [];
page.on("response", response => {
  if (response.url().includes(session)) requests.push({ url: response.url(), status: response.status() });
});
page.on("pageerror", error => errors.push(error.message));
try {
  await page.goto("http://127.0.0.1:8090", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Scanner", exact: true }).click();
  if (kind === "adaptive") {
    await page.getByRole("table", { name: "Adaptive capture history" }).waitFor();
    for (let index = 0; index < 10 && !await page.getByRole("button").filter({ hasText: session }).count(); index++) {
      const next = page.getByRole("button", { name: "Next adaptive captures", exact: true });
      if (!await next.isEnabled()) break;
      await Promise.all([
        page.waitForResponse(response => response.url().includes("/adaptive-sessions?") && response.status() === 200),
        next.click(),
      ]);
      await page.getByRole("table", { name: "Adaptive capture history" }).waitFor();
    }
  }
  await page.getByRole("button").filter({ hasText: session }).click({ timeout: 30000 });
  if (kind === "adaptive") {
    const panel = page.getByRole("region", { name: "Adaptive fractional analysis" });
    await panel.getByText("Figures ready", { exact: true }).waitFor({ timeout: 30000 });
    for (const img of await panel.locator("img").all()) {
      await img.scrollIntoViewIfNeeded();
      await img.evaluate(image => image.decode());
      const geometry = await img.evaluate(image => ({ src: image.src,
        width: image.naturalWidth, height: image.naturalHeight, alt: image.alt }));
      if (!geometry.width) throw new Error("empty image");
      figures.push(geometry);
      await img.screenshot({ path: join(output, `figure-${figures.length}.png`) });
    }
  } else {
    for (const name of ["Coverage", "GLRT64 vs time", "CFO vs time"]) {
      await page.getByRole("tab", { name, exact: true }).click({ timeout: 30000 });
      const img = page.locator("#persistent-artifact-image img");
      await img.scrollIntoViewIfNeeded();
      await img.evaluate(image => image.decode());
      figures.push(await img.evaluate(image => ({ src: image.src,
        width: image.naturalWidth, height: image.naturalHeight, alt: image.alt })));
      await img.screenshot({ path: join(output, `figure-${figures.length}.png`) });
    }
  }
  if (figures.length !== 3 || errors.length) throw new Error("incomplete figures or page error");
  const result = { verified_at: new Date().toISOString(), kind, session, figures, requests, errors };
  await writeFile(join(output, "ui-verification.json"), JSON.stringify(result, null, 2), { flag: "wx" });
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
