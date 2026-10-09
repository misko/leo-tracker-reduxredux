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
function hard60Status() {
  const value = status();
  value.manifest.document.schema_version = 2;
  value.manifest.document.analysis_id = "scanner-regional-position-v2";
  value.manifest.document.methods = value.manifest.document.methods.slice(1);
  value.manifest.artifacts = value.manifest.artifacts.slice(1);
  return { ...value, manifest: { ...value.manifest, document: { ...value.manifest.document,
    configuration: { protocol: "sacramento-hard60-v1", run: { slope_half_width_hz_s: 60 } },
  } } };
}
function b7Status() {
  const value = hard60Status();
  value.manifest.document.schema_version = 3;
  value.manifest.document.analysis_id = "scanner-regional-position-v3";
  value.manifest.document.configuration.protocol = "sacramento-hard60-b7-v1";
  return value;
}
const pending = { session_id: "scan-test", state: "pending", manifest: null };
const response = (value: unknown) => ({ ok: true, json: async () => value });

it("preserves historical maps with an explicit legacy label", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) =>
    Promise.resolve(response(url.endsWith("v1") ? status() : pending))));
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
  expect(screen.getByText(/Historical T1AT\/V16 comparison/)).toBeInTheDocument();
});

it("prefers Hard60, renders one map and retains both RF arms", async () => {
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(response(url.endsWith("v3") ? pending : hard60Status())));
  vi.stubGlobal("fetch", fetcher);
  render(<RegionalPosition sessionId="scan-test" inputDigest={digest} />);
  const images = await screen.findAllByRole("img");
  expect(images).toHaveLength(1);
  expect(images[0]).toHaveAttribute("width", "1080");
  expect(images[0]).toHaveAttribute("height", "960");
  expect(images[0]).toHaveStyle({ width: "100%", objectFit: "contain" });
  expect(images[0]).toHaveAttribute("src",
    `/api/v1/scanner/tracking/scan-test/regional-position-v2/V16.png?sha256=${encodeURIComponent(digest)}`);
  expect(screen.getByText("Hard60 / V16")).toBeInTheDocument();
  expect(screen.getAllByText("5.79 km")).toHaveLength(2);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("prefers B7 over historical results and uses the V3 PNG", async () => {
  const fetcher = vi.fn().mockResolvedValue(response(b7Status()));
  vi.stubGlobal("fetch", fetcher);
  render(<RegionalPosition sessionId="scan-test" inputDigest={digest} />);
  const image = (await screen.findAllByRole("img"))[0];
  expect(image).toHaveAttribute("src",
    `/api/v1/scanner/tracking/scan-test/regional-position-v3/V16.png?sha256=${encodeURIComponent(digest)}`);
  expect(screen.getByText("B7 / Hard60")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("polls pending results and cancels polling on unmount", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn().mockResolvedValueOnce(response(pending))
    .mockResolvedValueOnce(response(pending)).mockResolvedValueOnce(response(pending))
    .mockResolvedValue(response(b7Status()));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<RegionalPosition sessionId="scan-test" />);
  await act(async () => {});
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(screen.getAllByRole("img")).toHaveLength(1);
  view.unmount();
  await vi.advanceTimersByTimeAsync(30000);
  expect(fetcher).toHaveBeenCalledTimes(4);
});

it.each(["capture", "prior", "inventory", "truth", "arms"])("rejects incompatible %s evidence", async kind => {
  const value = b7Status();
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
  const value = b7Status();
  for (const method of value.manifest.document.methods) {
    method.state = "insufficient";
    for (const arm of method.arms) { arm.selected = null; arm.reasons = ["no-qualified-windows"]; }
  }
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(value)));
  render(<RegionalPosition sessionId="scan-test" />);
  expect(await screen.findAllByRole("img")).toHaveLength(1);
  expect(screen.getAllByText("Unavailable: no-qualified-windows")).toHaveLength(2);
});
