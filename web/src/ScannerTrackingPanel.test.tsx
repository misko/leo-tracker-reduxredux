import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ScannerTrackingPanel } from "./ScannerTrackingPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const product = {
  session_id: "scan-test", input_manifest_sha256: "sha256:test", sample_rate_hz: 2500000,
  trajectory_state: "complete", tle_state: "unavailable", reasons: [],
  physical_group_count: 8, eligible_group_count: 4, attempted_group_count: 4, deferred_group_count: 0,
  catalogue_exclusions: [{ catalog_number: 69730, name: "STARLINK-34343 DEB", reason: "catalogue-labelled-debris" }],
  unscored_groups: [{ physical_group_id: "group", reason: "catalogue population propagation is incomplete" }],
  tle_candidates: [], artifacts: [
    { name: "trajectory", sha256: "a" },
    { name: "trajectory-tle", sha256: "b" },
    { name: "tle-review-01", sha256: "c" },
  ],
};

it.each([2500000, 5000000, 10000000])("shows every published figure and actual failures at %s samples/s", async rate => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", state: "complete", phase: "complete", product: { ...product, sample_rate_hz: rate } }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" inputDigest="sha256:test" />);
  expect(await screen.findByText(/catalogue population propagation is incomplete/)).toBeInTheDocument();
  expect(screen.queryByText(/No group has the required/)).not.toBeInTheDocument();
  const images = screen.getAllByRole("img");
  expect(images).toHaveLength(3);
  expect(images[0]).toHaveAttribute("src", expect.stringContaining("/trajectory.png"));
  expect(images[1]).toHaveAttribute("src", expect.stringContaining("trajectory-tle.png"));
  expect(images[2]).toHaveAttribute("src", expect.stringContaining("tle-review-01.png"));
  expect(screen.getByText("Per-track TLE review 1")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Open .* PNG/ })).toHaveLength(3);
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
  expect((await screen.findAllByRole("img"))[0]).toHaveAttribute("src", expect.stringContaining("/trajectory.png"));
  expect(screen.getByText(/catalogue comparisons are still processing/)).toBeInTheDocument();
});

it("distinguishes relative trajectories from unavailable catalogue timing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    session_id: "scan-test", state: "complete", phase: "complete", product: {
      ...product,
      trajectory_state: "complete",
      trajectory_time_basis: "device-counter-relative",
      tle_state: "unavailable",
      physical_group_count: 46,
      eligible_group_count: 21,
      attempted_group_count: 0,
      deferred_group_count: 21,
      reasons: ["Measured trajectories use device-counter timing; TLE comparison requires qualified absolute UTC."],
      artifacts: [product.artifacts[0]],
    },
  }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" />);
  expect(await screen.findByText(/Relative trajectories are available/)).toBeInTheDocument();
  expect(screen.getByText(/21 eligible of 46 groups/)).toBeInTheDocument();
  expect(screen.getAllByRole("img")[0]).toHaveAttribute("src", expect.stringContaining("/trajectory.png"));
});

it("shows randomized leader persistence and runner margin", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    session_id: "scan-test", state: "complete", phase: "complete", product: {
      ...product,
      tle_candidates: [{
        physical_group_id: "group-66601", leading_catalog_number: 66601,
        support_span_s: 32.3, abstention_recommended: false, abstention_reasons: [],
        leading_candidate_persisted_on_heldout: true,
        heldout_runner_negative_log_score_margin: 0.494878855,
      }],
    },
  }) }));
  render(<ScannerTrackingPanel sessionId="scan-test" />);
  expect(await screen.findByText("NORAD 66601")).toBeInTheDocument();
  expect(screen.getByText("Leader retained · runner +0.495 NLL")).toBeInTheDocument();
  expect(screen.getByText("Candidate survived controls")).toBeInTheDocument();
});
