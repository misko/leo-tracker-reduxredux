import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AdaptiveRelativePhase, parseRelativePhase } from "./AdaptiveRelativePhase";

const digest = `sha256:${"1".repeat(64)}`;
const status = { schema_version: 1, session_id: "test", input_manifest_sha256: digest, binding_sha256: digest, state: "ready",
  manifest: { binding_sha256: digest, total_visit_count: 200, selected_visits: [1, 2], supported_visit_count: 2, pilot_checked_visit_count: 1,
    geometric_phase_claimed: false, phase_continuity_across_retunes: false,
    artifacts: [{ name: "relative-phase-overview", sha256: digest, byte_count: 200 }, { name: "relative-phase-dwells", sha256: `sha256:${"2".repeat(64)}`, byte_count: 300 }] } };
afterEach(() => vi.unstubAllGlobals());
test("renders both digest-bound phase PNGs with coverage and limitations", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => status }));
  render(<AdaptiveRelativePhase sessionId="test" />);
  await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
  expect(screen.getByText(/2 selected \/ 200/)).toBeTruthy();
  expect(screen.getByText(/not calibrated geometric phase/)).toBeTruthy();
  expect(screen.getAllByRole("img")[0].getAttribute("src")).toContain("binding_sha256=sha256%3A");
});
test("rejects source changes and geometric-phase claims", () => {
  expect(() => parseRelativePhase(status, "other")).toThrow();
  expect(() => parseRelativePhase({ ...status, manifest: { ...status.manifest, geometric_phase_claimed: true } }, "test")).toThrow();
});
test("shows pending without inventing a PNG", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...status, state: "pending", manifest: null }) }));
  render(<AdaptiveRelativePhase sessionId="test" />);
  expect(await screen.findByText(/queued or running/)).toBeTruthy();
  expect(screen.queryByRole("img")).toBeNull();
});
