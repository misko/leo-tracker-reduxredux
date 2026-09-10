// @vitest-environment node
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const report = "2026_09_10_scanner_cooperative_skips_checkpoint";
const publicRoot = new URL("./public/reports/scanner-2026-09-10/", import.meta.url);
const figures = ["capture-vs-screening.png", "desktop-stage-profile.png", "screening-by-target.png"];
// Historical reports are deliberately absent from immutable releases. This
// small projection travels with the web tests; repository-owned Python tests
// additionally bind it and these public bytes to the original report figures.
const index = JSON.parse(readFileSync(new URL("./report-assets.manifest.json", import.meta.url), "utf8"));

describe("published scanner report PNGs", () => {
  it("publishes only the three reviewed figures", () => {
    expect(index.schema_version).toBe(1);
    expect(index.report).toBe(report);
    expect(index.artifacts.map((entry) => entry.path).sort()).toEqual(
      figures.map((name) => `figures/${report}/${name}`).sort(),
    );
    expect(readdirSync(fileURLToPath(publicRoot)).sort()).toEqual([...figures].sort());
  });

  it.each(figures)("serves the exact hash-bound report figure %s", (name) => {
    const bytes = readFileSync(new URL(name, publicRoot));
    const sourcePath = `figures/${report}/${name}`;
    const artifact = index.artifacts.find((entry) => entry.path === sourcePath);
    expect(bytes.length).toBe(artifact.bytes);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(artifact.sha256);
    expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(bytes.readUInt32BE(16)).toBeGreaterThan(1000);
    expect(bytes.readUInt32BE(20)).toBeGreaterThan(500);
  });
});
