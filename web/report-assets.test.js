// @vitest-environment node
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const publicRoot = new URL("./public/reports/scanner-2026-09-10/", import.meta.url);
// Unchanged pins from reports/evidence/2026_09_10_scanner_cooperative_skips_checkpoint/index.json
// (SHA-256 68935e374a89353eaabc6107ad527073e397a126fc40b6af611831c2a566f77e).
// Immutable releases contain web/ but intentionally omit the historical reports/ tree.
const figures = [
  { name: "capture-vs-screening.png", bytes: 93829,
    sha256: "5dd7c313f08a4e4d2bc84845cf5ad82b60192d5c255d0794c1ddd3a7ce791c07" },
  { name: "desktop-stage-profile.png", bytes: 96207,
    sha256: "4b4ac3215c42ce4303a94be8d066507521e55ccec8eeb60d7d21e6153cb0f148" },
  { name: "screening-by-target.png", bytes: 95411,
    sha256: "2c18d8bea6ad0b9ddb0902f36e1a43857333292ba6e766f027cfe4932d4e806b" },
];

describe("published scanner report PNGs", () => {
  it("publishes only the three reviewed figures", () => {
    expect(readdirSync(fileURLToPath(publicRoot)).sort()).toEqual(figures.map(({ name }) => name).sort());
  });

  it.each(figures)("serves the exact hash-bound report figure $name", (artifact) => {
    const { name } = artifact;
    const bytes = readFileSync(new URL(name, publicRoot));
    expect(bytes.length).toBe(artifact.bytes);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(artifact.sha256);
    expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(bytes.readUInt32BE(16)).toBeGreaterThan(1000);
    expect(bytes.readUInt32BE(20)).toBeGreaterThan(500);
  });
});
