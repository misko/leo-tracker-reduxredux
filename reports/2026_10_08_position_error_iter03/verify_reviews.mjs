// Verify a normal new scan in the real WebUI; no mocks or DOM modifications.
import { chromium } from "../../web/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";

const [base, session, directory] = process.argv.slice(2);
await mkdir(directory, { recursive: true });
const endpoint = `${base}/api/v1/scanner/tracking/${session}`;
const response = await fetch(endpoint);
if (!response.ok) throw new Error(`Tracking HTTP ${response.status}`);
const status = await response.json();
const product = status.product;
if (status.state !== "complete" || product.review_limit !== 16 || product.review_count !== 16)
  throw new Error("New publication does not use 16 reviews");
const reviews = product.track_reviews;
const spans = reviews.map(r => r.end_s - r.start_s);
if (spans.some((span, i) => i && span > spans[i - 1] + 1e-8))
  throw new Error("Review support spans are not descending");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto(`${base}/?scan_id=${session}`, { waitUntil: "domcontentloaded" });
  const panel = page.getByRole("region", { name: "Shared satellite trajectory tracking", exact: true });
  await panel.getByText(/16 of .* eligible track reviews rendered/).waitFor({ timeout: 60000 });
  const images = panel.locator('img[alt^="tle-review-"]');
  if (await images.count() !== 16) throw new Error("Wrong number of review images in WebUI");
  const receipts = [];
  for (let i = 0; i < 16; i++) {
    const image = images.nth(i);
    await image.scrollIntoViewIfNeeded();
    const dimensions = await image.evaluate(async element => {
      await element.decode();
      return { width: element.naturalWidth, height: element.naturalHeight,
        layoutWidth: element.getBoundingClientRect().width };
    });
    if (dimensions.width < 100 || dimensions.height < 100 || dimensions.layoutWidth <= 0)
      throw new Error("Review image did not decode or render");
    const url = new URL(await image.getAttribute("src"), base);
    const png = await fetch(url);
    if (png.status !== 200 || png.headers.get("content-type") !== "image/png")
      throw new Error("Review PNG unavailable");
    const bytes = Buffer.from(await png.arrayBuffer());
    const digest = "sha256:" + createHash("sha256").update(bytes).digest("hex");
    if (digest !== url.searchParams.get("sha256")) throw new Error("Review hash mismatch");
    receipts.push({ url: url.href, sha256: digest, bytes: bytes.length, dimensions });
    if (i === 0) await image.screenshot({ path: `${directory}/first-review.png` });
  }
  if (errors.length) throw new Error(`Browser errors: ${errors}`);
  await writeFile(`${directory}/browser.json`, JSON.stringify({ session_id: session,
    checked_at: new Date().toISOString(), review_limit: product.review_limit,
    review_count: product.review_count, eligible: product.review_eligible_count,
    deferred: product.deferred_review_count, reviews, images: receipts, page_errors: errors,
    summary: await panel.getByText(/16 of .* eligible track reviews rendered/).innerText(),
  }, null, 2) + "\n");
  console.log(`Verified ${receipts.length} real WebUI review PNGs for ${session}`);
} finally {
  await browser.close();
}
