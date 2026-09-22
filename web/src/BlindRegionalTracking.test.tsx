import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BlindRegionalTracking } from "./BlindRegionalTracking";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const document = {
  session_id: "scan-test", input_manifest_sha256: "sha256:input", state: "diagnostic", reasons: [],
  known_position_used_for_association: false, known_position_used_for_inference: false, site_conditioned_candidates: false,
  region: { center_latitude_deg: 39.7392, center_longitude_deg: -104.9903, width_km: 14484.096, height_km: 14484.096 },
  accounting: { track_count: 1, associated_track_count: 1, eligible_observation_count: 100, excluded_count: 0 },
  tracks: [{ track_id: "track-1", state: "associated", catalogue_size: 9000, unassigned_weight: 0.1, reasons: [], candidates: [{ catalog_number: 12345, soft_weight: 0.8 }] }],
  position_modes: [{ rank: 1, state: "diagnostic", latitude_deg: 37.9, longitude_deg: -122.4, training_score: 10, heldout_score: 8, reasons: [] }],
  evaluation: { modes: [{ rank: 1, horizontal_error_m: 9000 }] },
};
function response(doc = document) {
  return { ok: true, json: async () => ({ session_id: "scan-test", state: "complete", manifest: { document: doc,
    artifacts: ["blind-association", "blind-position", "blind-position-modes"].map(name => ({ name, sha256: "sha256:png" })) } }) };
}
it("shows independent association, declared prior, error and all verified-artifact URLs", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));
  render(<BlindRegionalTracking sessionId="scan-test" inputDigest="sha256:input" />);
  expect(await screen.findByText("37.900000°, -122.400000°")).toBeInTheDocument();
  expect(screen.getByText("9.000 km")).toBeInTheDocument();
  expect(screen.getByText(/east\/west ±7242 km/)).toBeInTheDocument();
  expect(screen.getByText("NORAD 12345: 80.0%")).toBeInTheDocument();
  const images = screen.getAllByRole("img");
  expect(images).toHaveLength(3);
  expect(images[0]).toHaveAttribute("src", expect.stringContaining("/blind-regional/blind-association.png?sha256=sha256%3Apng"));
});
it.each([
  { ...document, input_manifest_sha256: "sha256:other" },
  { ...document, known_position_used_for_association: true },
])("rejects wrong capture or site-conditioned output", async doc => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(doc)));
  render(<BlindRegionalTracking sessionId="scan-test" inputDigest="sha256:input" />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
it("keeps blind pending distinct from the available assisted path", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", state: "pending", manifest: null }) }));
  render(<BlindRegionalTracking sessionId="scan-test" />);
  expect(await screen.findByText(/Blind association and positioning are pending/)).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
