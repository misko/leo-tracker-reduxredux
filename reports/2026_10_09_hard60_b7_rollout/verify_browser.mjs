// Verify the actual deployed page, with no network mocks or DOM edits.
import { chromium } from "../../web/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";

const [base, session, directory, expectedConfiguration] = process.argv.slice(2);
await mkdir(directory, { recursive: true });
const endpoint = `${base}/api/v1/scanner/tracking/${session}/regional-position-v3`;
const response = await fetch(endpoint);
if (!response.ok) throw new Error(`API HTTP ${response.status}`);
const status = await response.json();
if (status.state !== "complete") throw new Error("Publication incomplete");
const document = status.manifest.document;
if (document.configuration_sha256 !== expectedConfiguration)
  throw new Error("Unexpected configuration digest");
if (document.configuration.joint_policy.policy !== "hard60-b7-v1") throw new Error("B7 policy missing");
if (document.configuration.run.recovery_policy !== "failed-coarse-box-v1")
  throw new Error("Recovery policy is not active");
if (document.diagnostics.recovery?.policy !== "failed-coarse-box-v1")
  throw new Error("Recovery did not run");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1700 } });
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  await page.goto(`${base}/?scan_id=${session}`, { waitUntil: "domcontentloaded" });
  const panel = page.getByRole("region", { name: "Hard60 Sacramento positioning", exact: true });
  await panel.getByRole("heading", { name: "B7 / Hard60", exact: true }).waitFor({ timeout: 60000 });
  const image = panel.getByRole("img");
  if (await image.count() !== 1) throw new Error("Expected one Hard60 image");
  await image.scrollIntoViewIfNeeded();
  const dimensions = await image.evaluate(async element => {
    await element.decode();
    return {
      width: element.naturalWidth, height: element.naturalHeight,
      layoutWidth: element.getBoundingClientRect().width,
    };
  });
  if (dimensions.width !== 1080 || dimensions.height !== 960 || dimensions.layoutWidth <= 0)
    throw new Error("PNG did not decode or render");
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState("networkidle", { timeout: 15000 });
  await panel.scrollIntoViewIfNeeded();
  const url = new URL(await image.getAttribute("src"), base);
  if (!url.pathname.endsWith("/regional-position-v3/V16.png"))
    throw new Error("Wrong image endpoint");
  const png = await fetch(url);
  if (png.status !== 200 || png.headers.get("content-type") !== "image/png")
    throw new Error("PNG endpoint failed");
  const bytes = Buffer.from(await png.arrayBuffer());
  const digest = "sha256:" + createHash("sha256").update(bytes).digest("hex");
  if (digest !== url.searchParams.get("sha256")) throw new Error("PNG hash mismatch");
  const alerts = await panel.getByRole("alert").count();
  if (alerts || errors.length) throw new Error(`Browser errors: ${errors}, alerts: ${alerts}`);
  const trackingResponse = await fetch(`${base}/api/v1/scanner/tracking/${session}`);
  const tracking = await trackingResponse.json();
  if (tracking.product?.review_limit !== 16 || tracking.product?.review_count > 16)
    throw new Error("Longest-16 review limit not preserved");
  const reviewImages = await page.locator('img[alt^="tle-review-"]').count();
  if (reviewImages > 16) throw new Error("Too many rendered per-track images");
  const receipt = {
    review_limit: tracking.product.review_limit, review_count: tracking.product.review_count,
    review_selection_policy: tracking.product.review_selection_policy, review_images: reviewImages,
    session_id: session, url: page.url(), configuration_sha256: expectedConfiguration,
    recovery_attempted: document.diagnostics.recovery.attempted_points,
    recovery_converged: document.diagnostics.recovery.converged_points,
    arms: document.methods[0].arms, png_url: url.href, png_sha256: digest,
    png_bytes: bytes.length, dimensions, alerts, page_errors: errors,
    table: await panel.getByRole("table").innerText(), checked_at: new Date().toISOString(),
  };
  await panel.screenshot({ path: `${directory}/panel.png` });
  await writeFile(`${directory}/V16.png`, bytes);
  await writeFile(`${directory}/document.json`, JSON.stringify(document, null, 2) + "\n");
  await writeFile(`${directory}/browser.json`, JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify(receipt));
} finally {
  await browser.close();
}
