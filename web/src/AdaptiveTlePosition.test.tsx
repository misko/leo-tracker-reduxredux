import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdaptiveTlePosition } from "./AdaptiveTlePosition";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const document = {
  schema_version: 2, analysis_id: "scanner-adaptive-tle-position-v2",
  session_id: "scan-test", input_manifest_sha256: "sha256:input", state: "diagnostic", reasons: [] as string[],
  known_position_used_for_inference: false, position_fix_claimed: false,
  priors: [{ name: "sacramento", region: { radius_km: 250 }, search_complete: false,
    accounting: { eligible_track_count: 34, eligible_observation_count: 750, evaluated_point_count: 400 },
    selected: { latitude_deg: 37.9, longitude_deg: -122.4, capped_weighted_rmse_hz: 184.78, spacing_km: 50 } }],
};
function response(doc = document) {
  return { ok: true, json: async () => ({ session_id: "scan-test", state: "complete", manifest: {
    document: doc, artifacts: [{ name: "map", sha256: "sha256:png" }],
  } }) };
}
it("publishes a digest-bound PNG and machine-readable result with selection limitations", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));
  render(<AdaptiveTlePosition sessionId="scan-test" inputDigest="sha256:input" />);
  const image = await screen.findByRole("img");
  expect(image).toHaveAttribute("src", "/api/v1/scanner/tracking/scan-test/adaptive-tle-position-v2/map.png?sha256=sha256%3Apng");
  expect(screen.getByRole("link", { name: "Download adaptive position JSON" })).toHaveAttribute("href", "/api/v1/scanner/tracking/scan-test/adaptive-tle-position-v2");
  expect(screen.getByText("Sacramento · 250 km")).toBeInTheDocument();
  expect(screen.getByText(/not an independent accuracy test/)).toBeInTheDocument();
  expect(screen.getByText("34 tracks · 750 observations")).toBeInTheDocument();
  expect(screen.getByText("400 positions · budget limited")).toBeInTheDocument();
  expect(screen.getByText("184.78 Hz")).toBeInTheDocument();
});
it.each([
  { ...document, input_manifest_sha256: "sha256:other" },
  { ...document, session_id: "another-scan" },
  { ...document, known_position_used_for_inference: true },
  { ...document, position_fix_claimed: true },
  { ...document, schema_version: 1 },
  { ...document, priors: [{ ...document.priors[0], region: { radius_km: 500 } }] },
])("rejects mismatched or incompatible evidence", async doc => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(doc)));
  render(<AdaptiveTlePosition sessionId="scan-test" inputDigest="sha256:input" />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
it("shows an explicit reason for insufficient evidence", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...document, state: "insufficient", reasons: ["no-eligible-tracks"], priors: [] })));
  render(<AdaptiveTlePosition sessionId="scan-test" />);
  expect(await screen.findByText("insufficient: no-eligible-tracks")).toBeInTheDocument();
});
it("keeps missing analysis pending without inventing a position", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ session_id: "scan-test", state: "pending", manifest: null }) }));
  render(<AdaptiveTlePosition sessionId="scan-test" />);
  expect(await screen.findByText("Adaptive position analysis is pending.")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
