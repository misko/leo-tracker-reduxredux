import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RegionalPosition } from "./RegionalPosition";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const digest = `sha256:${"a".repeat(64)}`;
function status() {
  return {
    session_id: "scan-test", state: "complete", manifest: {
      document: {
        schema_version: 1, analysis_id: "scanner-regional-position-v1", session_id: "scan-test",
        input_manifest_sha256: digest, prior_latitude_deg: 38.5816, prior_longitude_deg: -121.4944,
        prior_radius_km: 250, known_position_used_for_inference: false, position_fix_claimed: false,
        refinement: "off", windows: 100,
        rf_ablation_scope: "final-score-shared-fitted-c-calibration-and-association",
        methods: ["T1AT", "V16"].map(name => ({ name, state: "diagnostic", points: [],
          search_stop_reason: "budget-exhausted", deferred_cells: 12,
          arms: ["fitted-c", "zero-c"].map(arm => ({ name: arm, reasons: [] as string[], selected: {
            latitude_deg: 37.9, longitude_deg: -122.4, horizontal_error_m: 5790,
            posterior_rms_hz: 123, coefficient_hz_per_ghz: 0, converged: true, boundary: false,
          } as null | { latitude_deg: number; longitude_deg: number; horizontal_error_m: number;
            posterior_rms_hz: number; coefficient_hz_per_ghz: number; converged: boolean; boundary: boolean } })),
        })),
      },
      artifacts: ["T1AT", "V16"].map(name => ({ name, sha256: digest })),
    },
  };
}
const response = (value: unknown) => ({ ok: true, json: async () => value });

it("shows both automatic maps, both RF arms and reference errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(status())));
  render(<RegionalPosition sessionId="scan-test" inputDigest={digest} />);
  expect(await screen.findAllByRole("img")).toHaveLength(2);
  for (const name of ["T1AT", "V16"]) {
    // Reserve the renderer's intrinsic size so lazy images can intersect the
    // viewport before loading; a zero-size grid item never triggers Chromium.
    const image = screen.getByRole("img", { name: `${name} Sacramento position search for scan-test` });
    expect(image).toHaveAttribute("width", "1080");
    expect(image).toHaveAttribute("height", "960");
    expect(image).toHaveStyle({ width: "100%", objectFit: "contain" });
    expect(screen.getByRole("link", { name: `Open ${name} position PNG` })).toHaveAttribute("href",
      `/api/v1/scanner/tracking/scan-test/regional-position-v1/${name}.png?sha256=${encodeURIComponent(digest)}`);
  }
  expect(screen.getAllByText("5.79 km")).toHaveLength(4);
  expect(screen.getAllByText("c = 0")).toHaveLength(2);
  expect(screen.getAllByText("123.0 Hz")).toHaveLength(4);
});

it("polls pending results and cancels polling on unmount", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn().mockResolvedValueOnce(response({ session_id: "scan-test", state: "pending", manifest: null }))
    .mockResolvedValue(response(status()));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<RegionalPosition sessionId="scan-test" />);
  await act(async () => {});
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(screen.getAllByRole("img")).toHaveLength(2);
  view.unmount();
  await vi.advanceTimersByTimeAsync(30000);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it.each(["capture", "prior", "inventory", "truth", "arms"])("rejects incompatible %s evidence", async kind => {
  const value = status();
  if (kind === "capture") value.manifest.document.input_manifest_sha256 = "other";
  if (kind === "prior") value.manifest.document.prior_radius_km = 500;
  if (kind === "inventory") value.manifest.artifacts.pop();
  if (kind === "truth") value.manifest.document.known_position_used_for_inference = true;
  if (kind === "arms") value.manifest.document.methods[0].arms.pop();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(value)));
  render(<RegionalPosition sessionId="scan-test" inputDigest={digest} />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("keeps diagnostic maps visible when evidence is insufficient", async () => {
  const value = status();
  for (const method of value.manifest.document.methods) {
    method.state = "insufficient";
    for (const arm of method.arms) { arm.selected = null; arm.reasons = ["no-qualified-windows"]; }
  }
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(value)));
  render(<RegionalPosition sessionId="scan-test" />);
  expect(await screen.findAllByRole("img")).toHaveLength(2);
  expect(screen.getAllByText("Unavailable: no-qualified-windows")).toHaveLength(4);
});
