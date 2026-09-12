import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ScannerTrackingPanel } from "./ScannerTrackingPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const product = {
  session_id: "scan-test", input_manifest_sha256: "sha256:test", sample_rate_hz: 2500000,
  trajectory_state: "complete", tle_state: "unavailable", reasons: [],
  physical_group_count: 8, eligible_group_count: 4, attempted_group_count: 4, deferred_group_count: 0,
  catalogue_exclusions: [{ catalog_number: 69730, name: "STARLINK-34343 DEB", reason: "catalogue-labelled-debris" }],
  unscored_groups: [{ physical_group_id: "group", reason: "catalogue population propagation is incomplete" }],
  tle_candidates: [], artifacts: [{ name: "trajectory", sha256: "a" }, { name: "trajectory-tle", sha256: "b" }],
};

it.each([2500000, 5000000])("shows figures and actual failures at %s samples/s", async rate => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", state: "complete", phase: "complete", product: { ...product, sample_rate_hz: rate } }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" inputDigest="sha256:test" />);
  expect(await screen.findByText(/catalogue population propagation is incomplete/)).toBeInTheDocument();
  expect(screen.queryByText(/No group has the required/)).not.toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAttribute("src", expect.stringContaining("trajectory-tle.png"));
  fireEvent.click(screen.getByRole("tab", { name: "Measured trajectories" }));
  expect(screen.getByRole("img")).toHaveAttribute("src", expect.stringContaining("/trajectory.png"));
  expect(screen.getByRole("link", { name: "Download tracking evidence" })).toBeInTheDocument();
});

it("rejects a product belonging to another capture", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", product }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" inputDigest="sha256:different" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("does not match");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("keeps the measured PNG visible while matching is pending", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", state: "running", phase: "tle-matching", product: { ...product, tle_state: "pending", artifacts: [product.artifacts[0]] } }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" />);
  expect(await screen.findByRole("img")).toHaveAttribute("src", expect.stringContaining("/trajectory.png"));
  expect(screen.getByText(/catalogue comparisons are still processing/)).toBeInTheDocument();
});
