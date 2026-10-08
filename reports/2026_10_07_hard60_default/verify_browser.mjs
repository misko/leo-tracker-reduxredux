// Real Chromium verification: no DOM edits, mocked network or injected images.
import { chromium } from "../../web/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { isDeepStrictEqual } from "node:util";

const [base, session, directory] = process.argv.slice(2);
const endpoint = `${base}/api/v1/scanner/tracking/${encodeURIComponent(session)}/regional-position-v2`;
const response = await fetch(endpoint);
if (response.status !== 200) throw new Error("Live publication API failed");
const status = await response.json();
if (status.state !== "complete" || !status.manifest)
  throw new Error("Live Hard60 publication is not complete");
const document = status.manifest.document;
const qualified = JSON.parse(await readFile(`${directory}/qualified-document.json`, "utf8"));
const matchedFields = [
  "schema_version", "analysis_id", "session_id", "input_manifest_sha256",
  "analysis_manifest_sha256", "configuration_sha256", "evidence_sha256",
  "configuration", "windows", "methods",
];
for (const field of matchedFields)
  if (!isDeepStrictEqual(document[field], qualified[field]))
    throw new Error(`Live publication differs from qualification: ${field}`);
const matchedDiagnostics = ["checkpoint_binding", "retained_basins", "calibrations", "final_starts"];
for (const field of matchedDiagnostics)
  if (!isDeepStrictEqual(document.diagnostics[field], qualified.diagnostics[field]))
    throw new Error(`Live numerical evidence differs: ${field}`);
const qualifiedPng = await readFile(`${directory}/qualified-hard60.png`);
const qualifiedDigest = "sha256:" + createHash("sha256").update(qualifiedPng).digest("hex");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1700 } });
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  await page.goto(`${base}/?scan_id=${encodeURIComponent(session)}`, {
    waitUntil: "domcontentloaded", timeout: 60000,
  });
  const panel = page.getByRole("region", { name: "Hard60 Sacramento positioning", exact: true });
  await panel.getByRole("heading", { name: "Hard60 / V16", exact: true }).waitFor({ timeout: 60000 });
  const image = panel.getByRole("img");
  if (await image.count() !== 1) throw new Error("Hard60 must render exactly one map");
  await image.scrollIntoViewIfNeeded();
  await image.evaluate(async element => {
    await element.decode();
    if (element.naturalWidth !== 1080 || element.naturalHeight !== 960)
      throw new Error("Wrong decoded PNG dimensions");
    if (element.getBoundingClientRect().width <= 0) throw new Error("Image has no layout width");
  });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState("networkidle", { timeout: 15000 });
  await panel.scrollIntoViewIfNeeded();
  let previousBox = null;
  let stable = 0;
  for (let attempt = 0; attempt < 30 && stable < 4; attempt += 1) {
    await page.waitForTimeout(250);
    const box = await panel.boundingBox();
    stable = isDeepStrictEqual(box, previousBox) ? stable + 1 : 0;
    previousBox = box;
  }
  if (stable < 4) throw new Error("Page layout did not settle before screenshot");
  if (await panel.getByRole("alert").count()) throw new Error("Hard60 panel contains an alert");
  const src = await image.getAttribute("src");
  if (!src.includes("/regional-position-v2/V16.png")) throw new Error("Historical image was shown");
  const url = new URL(src, base);
  const png = await fetch(url);
  if (png.status !== 200 || png.headers.get("content-type") !== "image/png")
    throw new Error("PNG route failed");
  const bytes = Buffer.from(await png.arrayBuffer());
  const digest = "sha256:" + createHash("sha256").update(bytes).digest("hex");
  if (digest !== url.searchParams.get("sha256")) throw new Error("PNG digest differs");
  if (digest !== qualifiedDigest) throw new Error("Live PNG differs from qualified figure");
  const result = {
    url: page.url(), title: await panel.getByRole("heading", { level: 5 }).innerText(),
    png_url: url.href, png_bytes: bytes.length, png_sha256: digest,
    image: await image.evaluate(element => ({
      complete: element.complete, natural_width: element.naturalWidth,
      natural_height: element.naturalHeight, layout_width: element.getBoundingClientRect().width,
    })),
    table: await panel.getByRole("table").innerText(),
    alerts: await panel.getByRole("alert").count(), page_errors: errors,
    checked_at: new Date().toISOString(),
  };
  await panel.screenshot({ path: `${directory}/live-hard60-panel.png` });
  await writeFile(`${directory}/browser-verification.json`, JSON.stringify(result, null, 2) + "\n");
  await writeFile(`${directory}/live-publication-verification.json`, JSON.stringify({
    endpoint, state: status.state, session_id: session,
    configuration_sha256: document.configuration_sha256,
    evidence_sha256: document.evidence_sha256,
    matched_document_fields: matchedFields, matched_diagnostics: matchedDiagnostics,
    png_sha256: digest, png_matches_qualification: true,
    checked_at: result.checked_at,
  }, null, 2) + "\n");
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
