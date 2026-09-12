import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ScannerRefinementPanel } from "./ScannerRefinementPanel";

const digest = `sha256:${"a".repeat(64)}`;
const fixture = () => ({ schema_version: 1, session_id: "scan-one", state: "complete", manifest: {
  session_id: "scan-one", input_manifest_sha256: digest, evidence_sha256: digest,
  sample_rate_hz: 5000000, scheduled_probes: 32, completed_probes: 31, failed_probes: 1,
  artifacts: ["shift-recovery", "probe-comparison"].map(name => ({ name, sha256: digest, byte_count: 100 })),
} });
afterEach(() => vi.unstubAllGlobals());

it("uses the versioned API to display a native 10 MS/s comparison", async () => {
  const value = fixture();
  value.schema_version = 2;
  value.manifest.sample_rate_hz = 10000000;
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => value });
  vi.stubGlobal("fetch", fetch);
  render(<ScannerRefinementPanel sessionId="scan-one" inputDigest={digest} />);
  expect(await screen.findByRole("img")).toHaveAttribute("src", expect.stringContaining("/api/v2/scanner/refinement-comparisons/scan-one/"));
  expect(screen.getByText(/10 MS\/s/)).toBeInTheDocument();
});

it("shows both saved PNG comparisons and preserves failure and accuracy context", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => fixture() }));
  render(<ScannerRefinementPanel sessionId="scan-one" inputDigest={digest} />);
  expect(await screen.findByRole("img")).toHaveAttribute("src", expect.stringContaining("shift-recovery.png"));
  expect(screen.getByText(/1 probe failures/)).toBeInTheDocument();
  expect(screen.getByText(/not absolute timing/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Individual probe errors" }));
  expect(screen.getByRole("img")).toHaveAttribute("src", expect.stringContaining("probe-comparison.png"));
  expect(screen.getByRole("link", { name: "Download numerical evidence" })).toHaveAttribute("href", expect.stringContaining("evidence.json"));
});

it("does not expose PNGs before publication or claim a running worker", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ schema_version: 1, session_id: "scan-one", state: "partial", manifest: null }) }));
  render(<ScannerRefinementPanel sessionId="scan-one" />);
  expect(await screen.findByRole("status")).toHaveTextContent("checkpoints are saved");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("rejects a comparison bound to another input manifest", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => fixture() }));
  render(<ScannerRefinementPanel sessionId="scan-one" inputDigest="different" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("does not match");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
