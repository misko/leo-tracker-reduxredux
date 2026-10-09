import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { getAdaptiveSessions, type AdaptivePage } from "./adaptive-api";
import { histogram, loadErrors, PositionErrorPanel } from "./PositionErrorPanel";
vi.mock("./adaptive-api", () => ({ getAdaptiveSessions: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });
const digest = `sha256:${"a".repeat(64)}`;
function page(ids: string[], next: number | null = null) {
  return { next_cursor: next, items: ids.map(session_id => ({ session_id,
    input_manifest_sha256: digest, captured_at: new Date(1000).toISOString() })) } as AdaptivePage;
}
function status(id: string, error: number | null = 1200) {
  return { session_id: id, state: "complete", manifest: { artifacts: [{ name: "V16", sha256: digest }], document: {
    schema_version: 3, analysis_id: "scanner-regional-position-v3", session_id: id, input_manifest_sha256: digest,
    prior_latitude_deg: 38.5816, prior_longitude_deg: -121.4944, prior_radius_km: 250,
    known_position_used_for_inference: false, position_fix_claimed: false, refinement: "off",
    rf_ablation_scope: "final-score-shared-fitted-c-calibration-and-association",
    configuration: { protocol: "sacramento-hard60-b7-v1", run: { slope_half_width_hz_s: 60 } },
    methods: [{ name: "V16", arms: ["fitted-c", "zero-c"].map(name => ({ name,
      selected: error === null ? null : { horizontal_error_m: error, converged: true } })) }],
  } } };
}
it("histogram retains zero, bin boundaries and the maximum exactly once", () => {
  expect(histogram([0, 1, 2, 12], 12)).toEqual([1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
});
it("paginates, deduplicates and converts metres; never replaces missing results with zero", async () => {
  vi.mocked(getAdaptiveSessions).mockResolvedValueOnce(page(["a", "b"], 10)).mockResolvedValueOnce(page(["a", "c"]));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () => status(url.includes("/b/") ? "b" : url.includes("/c/") ? "c" : "a", url.includes("/b/") ? null : 1200) })));
  const value = await loadErrors(0, 2000, 3, new AbortController().signal, () => {});
  expect(value.scans).toBe(3); expect(value.unavailable).toBe(1);
  expect(value.points.map(p => p.fitted)).toEqual([1.2, 1.2]);
  expect(fetch).toHaveBeenCalledTimes(3);
});
it("excludes out-of-range scans and counts invalid bindings separately", async () => {
  vi.mocked(getAdaptiveSessions).mockResolvedValue(page(["a"]));
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => status("wrong") })));
  expect((await loadErrors(0, 2000, 3, new AbortController().signal, () => {})).failed).toBe(1);
  expect((await loadErrors(2000, 3000, 3, new AbortController().signal, () => {})).scans).toBe(0);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("rejects negative errors and handles unavailable endpoints", async () => {
  vi.mocked(getAdaptiveSessions).mockResolvedValue(page(["a", "b"]));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes("/b/") ? { status: 404 } : { ok: true, json: async () => status("a", -1) }));
  const value = await loadErrors(0, 2000, 3, new AbortController().signal, () => {});
  expect(value.failed).toBe(1); expect(value.unavailable).toBe(1); expect(value.points).toEqual([]);
});
it("reports capped history coverage", async () => {
  vi.mocked(getAdaptiveSessions).mockImplementation(async cursor => page([], cursor + 10));
  expect((await loadErrors(0, 2000, 3, new AbortController().signal, () => {})).truncated).toBe(true);
});
it("stops paging once capture history precedes the selected range", async () => {
  vi.mocked(getAdaptiveSessions).mockResolvedValue(page(["old"], 10));
  const value = await loadErrors(2000, 3000, 3, new AbortController().signal, () => {});
  expect(getAdaptiveSessions).toHaveBeenCalledTimes(1);
  expect(value.truncated).toBe(false);
});
it("shows the empty state and validates adjustable dates", async () => {
  vi.mocked(getAdaptiveSessions).mockResolvedValue(page([]));
  render(<PositionErrorPanel />);
  expect(await screen.findByText("No position estimates for this time range and method.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-10-10T10:00" } });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-10-09T10:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Update plots" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Choose an end time after the start time");
});
it("renders both accessible charts and changes the requested method", async () => {
  const now = new Date(Date.now() - 1000).toISOString();
  const p = page(["a"]); p.items[0].captured_at = now;
  vi.mocked(getAdaptiveSessions).mockResolvedValue(p);
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => status("a") })));
  render(<PositionErrorPanel />);
  expect(await screen.findAllByRole("img")).toHaveLength(2);
  expect(screen.getByText("Fitted c: 1 estimates")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Position method"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Last 6 hours" }));
  await screen.findByText(/1 requests or verification checks failed/);
  expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toContain("regional-position-v2");
});
