import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
// Relative-phase fetching/rendering has its own component tests; keep these
// existing overview polling assertions scoped to the overview component.
vi.mock("./AdaptiveRelativePhase", () => ({ AdaptiveRelativePhase: () => <section aria-label="Broadband and pilot relative phase" /> }));
import { AdaptiveAnalysisPanel } from "./AdaptiveAnalysisPanel";
import { adaptiveFigureUrl, getAdaptiveAnalysis } from "./adaptive-analysis-api";
import type { AdaptiveAnalysisStatus } from "./adaptive-analysis-api";
import type { AdaptivePhaseStatus } from "./adaptive-phase-api";
import type { AdaptivePhaseV2Status } from "./adaptive-phase-v2-api";
import { adaptiveDetailFixture, hostAdaptiveDetailFixture, multirateAdaptiveDetailFixture } from "./adaptive-fixtures";

const capture = adaptiveDetailFixture().capture;
const respond = (value: unknown, status = 200) => ({ ok: status === 200, status, json: async () => value }) as Response;
const analysisFetch = (value: unknown) => vi.fn((url: string) => Promise.resolve(
  respond(url.includes("dual-rx-phase") ? null : value, url.includes("dual-rx-phase") ? 404 : 200),
));
const sha = (letter: string) => `sha256:${letter.repeat(64)}`;
export function analysisFixture(state: AdaptiveAnalysisStatus["state"] = "figures_ready"): AdaptiveAnalysisStatus {
  const complete = state === "figures_ready" || state === "metrics_complete";
  return {
    schema_version: 1, kind: "adaptive_hop_analysis_status", session_id: capture.session_id,
    input_manifest_sha256: capture.input_manifest_sha256, binding_sha256: sha("a"),
    configuration: { schema_version: 1, analyzer_id: "adaptive-hop-fractional-glrt64-cfo-v1", sample_rate_hz: capture.sample_rate_hz,
      valid_visit_ms: 120, probe_ms: 20, probe_stride_ms: 120, glrt64_margin_gate: .025, maximum_acquisition_candidates: 8,
      receiver_ids: [0, 1], timing_refinement: "circular-five-cell-log-parabola-plus-lanczos16-v1", decision_score: "fractional-epoch-conditioned-glrt64-v1" },
    total_visits: capture.retained_visits, checkpoint_visits: complete ? capture.retained_visits : state === "partial" ? 1 : 0,
    state, progress_basis: complete ? "sealed_metrics_manifest" : state === "partial" ? "file_inventory" : "no_checkpoints",
    worker_activity: "not_observed", metrics_manifest_sha256: complete ? sha("b") : null,
    overview: state !== "figures_ready" ? null : {
      schema_version: 1, kind: "adaptive_hop_fractional_overview", presentation_id: "adaptive-actual-visit-glrt64-overview-v1",
      session_id: capture.session_id, binding_sha256: sha("a"), metrics_manifest_sha256: sha("b"), finalized_utc_ns: "1789000000000000000",
      trajectory_configuration_sha256: sha("c"), trajectory_input_policy: "strongest-passed-fractional-candidate-per-visit-rx",
      trajectory_scope: "separate-target-and-receiver-candidate-associations", selected_observation_count: 2,
      association_count: 0, truncated_association_count: 1,
      artifacts: ["coverage", "glrt64-response", "cfo-trajectories"].map((name, i) => ({ name: name as "coverage" | "glrt64-response" | "cfo-trajectories", content_type: "image/png", sha256: sha("def"[i]), byte_count: 100 })),
    },
  };
}
function phaseFixture(sessionId = capture.session_id): AdaptivePhaseStatus {
  return {
    schema_version: 1, kind: "adaptive_dual_rx_phase_status", session_id: sessionId,
    input_manifest_sha256: capture.input_manifest_sha256, receiver_ids: [0, 1], state: "ready",
    reason: "published_phase_evidence", worker_activity: "not_observed",
    manifest: {
      schema_version: 1, kind: "adaptive_dual_rx_phase_manifest", analysis_id: "adaptive-qin-pilot-double-difference-v1",
      session_id: sessionId, input_manifest_sha256: capture.input_manifest_sha256,
      glrt_binding_sha256: sha("a"), glrt_metrics_manifest_sha256: sha("b"),
      state: "ready", reason: "published_phase_evidence", qualified_phase_count: 19,
      association_count: 3, finalized_utc_ns: "1789000000000000000",
      artifact: { name: "dual-rx-phase-progression", content_type: "image/png", sha256: sha("f"), byte_count: 541025 },
    },
  };
}
function phaseV2Fixture(sessionId = capture.session_id): AdaptivePhaseV2Status {
  return {
    schema_version: 2, kind: "adaptive_dual_rx_phase_status", session_id: sessionId,
    input_manifest_sha256: capture.input_manifest_sha256, receiver_ids: [0, 1], state: "ready",
    reason: "published_phase_time_hypotheses", checkpoint_visit_count: capture.retained_visits,
    total_visit_count: capture.retained_visits, worker_activity: "not_observed",
    manifest: {
      schema_version: 2, kind: "adaptive_dual_rx_phase_manifest", analysis_id: "adaptive-qin-pilot-double-difference-v2",
      session_id: sessionId, input_manifest_sha256: capture.input_manifest_sha256,
      glrt_binding_sha256: sha("a"), glrt_metrics_manifest_sha256: sha("b"), state: "ready",
      reason: "published_phase_time_hypotheses", total_visit_count: capture.retained_visits,
      checkpoint_visit_count: capture.retained_visits, qualified_visit_count: 4, hypothesis_count: 6,
      geometry_phase_state: "unavailable", geometry_phase_reason: "calibration unavailable",
      receiver_product: "rx1_times_conjugate_rx0", phase_continuity_across_retunes: false,
      association_uses_phase: false, aliases_resolved: false, pilot_phase_ambiguity: "modulo_pi", finalized_utc_ns: "1789000000000000000",
      artifact: { name: "dual-rx-double-difference-time", content_type: "image/png", sha256: sha("e"), byte_count: 1234 },
    },
  };
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("adaptive analysis publication", () => {
  it.each([15000000, 20000000] as const)("binds V3 analysis and all PNGs at %s S/s", async rate => {
    const native = multirateAdaptiveDetailFixture(rate).capture;
    const value = analysisFixture();
    value.schema_version = 3;
    Object.assign(value.configuration, { schema_version: 3, analyzer_id: "host-adaptive-native-15m-20m-fractional-glrt64-cfo-v3", sample_rate_hz: rate, receiver_ids: [0] });
    Object.assign(value.overview!, { schema_version: 3, presentation_id: "host-adaptive-native-15m-20m-overview-v3" });
    vi.stubGlobal("fetch", analysisFetch(value));
    render(<AdaptiveAnalysisPanel capture={native} />);
    expect(await screen.findAllByRole("img")).toHaveLength(3);
    expect(screen.getByText(new RegExp(`RX0 analyzed offline at ${rate / 1e6} MS/s`))).toBeInTheDocument();
    await expect(getAdaptiveAnalysis(native)).resolves.toEqual(value);
  });
  it.each([0, 1] as const)("links the site receiver-input RCA for radio003a RX%s", async receiver => {
    const native = hostAdaptiveDetailFixture(receiver).capture;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<AdaptiveAnalysisPanel capture={native} />);
    const link = await screen.findByRole("link", { name: "Read the RX0/RX1 detection root-cause analysis" });
    expect(link).toHaveAttribute("href", "/reports/radio003a-rx-input-rca.html");
    expect(screen.getByRole("complementary", { name: "Receiver input status" })).toHaveTextContent(
      receiver === 1 ? "RX1 has no connected antenna feed" : "RX0 is the connected antenna input",
    );
  });

  it("does not apply the site receiver-input finding to another radio", async () => {
    const native = { ...hostAdaptiveDetailFixture(1).capture, radio_serial: "different-radio" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<AdaptiveAnalysisPanel capture={native} />);
    await screen.findByText(/It is not queued here/);
    expect(screen.queryByRole("link", { name: "Read the RX0/RX1 detection root-cause analysis" })).not.toBeInTheDocument();
  });

  it("renders digest-bound dual-RX phase beside standard adaptive analysis", async () => {
    const historical = {
      ...capture,
      session_id: "scan-hop-bfc60ea18ace593b",
    };
    const value = analysisFixture();
    value.session_id = historical.session_id;
    value.input_manifest_sha256 = historical.input_manifest_sha256;
    value.overview!.session_id = historical.session_id;
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(respond(url.includes("dual-rx-phase") ? phaseFixture(historical.session_id) : value))));
    render(<AdaptiveAnalysisPanel capture={historical} />);
    const image = await screen.findByRole("img", {
      name: "GLRT tracks with dual-RX phase progression",
    });
    expect(image).toHaveAttribute(
      "src",
      expect.stringContaining("/api/v1/scanner/adaptive-sessions/scan-hop-bfc60ea18ace593b/analysis/dual-rx-phase/artifact.png?"),
    );
    expect(image.closest("figure")).toHaveAttribute(
      "data-artifact-sha256",
      sha("f"),
    );
    expect(image.closest("figure")).toHaveAttribute("data-artifact-bytes", "541025");
    expect(screen.getAllByRole("img")).toHaveLength(4);
    expect(screen.getByText(/19 qualified double-difference estimates/)).toBeInTheDocument();
    expect(screen.getByText(/supplemental evidence/)).toBeInTheDocument();
  });

  it("renders V2 phase time with explicit alias and geometry limits", async () => {
    const value = analysisFixture();
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url.includes("dual-rx-phase-v2") ? respond(phaseV2Fixture())
        : url.includes("dual-rx-phase") ? respond(null, 404) : respond(value),
    )));
    render(<AdaptiveAnalysisPanel capture={capture} />);
    const image = await screen.findByRole("img", { name: "Dual-RX phase versus time" });
    expect(image).toHaveAttribute("src", expect.stringContaining("dual-rx-phase-v2/artifact.png"));
    expect(screen.getByText(/CFO aliases and the pilot half-cycle phase branch remain unresolved/)).toBeInTheDocument();
    expect(screen.getByText(/Geometry phase: unavailable/)).toBeInTheDocument();
  });

  it("does not invent phase evidence for an unregistered or single-RX recording", async () => {
    vi.stubGlobal("fetch", analysisFetch(analysisFixture()));
    const view = render(<AdaptiveAnalysisPanel capture={capture} />);
    await screen.findByRole("img", { name: "Retained channel coverage" });
    expect(screen.queryByRole("img", { name: "GLRT tracks with dual-RX phase progression" })).not.toBeInTheDocument();
    view.unmount();

    const native = hostAdaptiveDetailFixture(0).capture;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<AdaptiveAnalysisPanel capture={{ ...native, session_id: "scan-hop-bfc60ea18ace593b" }} />);
    await screen.findByText(/It is not queued here/);
    expect(screen.queryByRole("img", { name: "GLRT tracks with dual-RX phase progression" })).not.toBeInTheDocument();
  });

  it.each([0, 1] as const)("binds native analysis and PNGs to physical RX%s", async receiver => {
    const native = hostAdaptiveDetailFixture(receiver).capture;
    const value = analysisFixture();
    value.schema_version = 2;
    Object.assign(value.configuration, { schema_version: 2, analyzer_id: "host-adaptive-native-10m-fractional-glrt64-cfo-v2", sample_rate_hz: 10000000, receiver_ids: [receiver] });
    Object.assign(value.overview!, { schema_version: 2, presentation_id: "host-adaptive-native-10m-overview-v2" });
    const fetcher = analysisFetch(value);
    vi.stubGlobal("fetch", fetcher);
    render(<AdaptiveAnalysisPanel capture={native} />);
    await screen.findByRole("img", { name: "Retained channel coverage" });
    expect(screen.getByText(new RegExp(`RX${receiver} analyzed offline at 10 MS/s`))).toBeInTheDocument();
    expect(fetcher.mock.calls[0][0]).toContain("/api/v2/");
    expect(adaptiveFigureUrl(value, value.overview!.artifacts[0])).toContain("/api/v2/");
    value.configuration.receiver_ids = [receiver === 0 ? 1 : 0];
    await expect(getAdaptiveAnalysis(native)).rejects.toThrow(/configuration/);
    value.configuration.receiver_ids = [receiver];
    value.overview!.selected_observation_count = native.retained_visits + 1;
    await expect(getAdaptiveAnalysis(native)).rejects.toThrow(/figures/);
  });
  it.each(["not_started", "partial", "metrics_complete", "figures_ready"] as const)("shows %s without inventing live-worker status", async state => {
    vi.stubGlobal("fetch", analysisFetch(analysisFixture(state)));
    render(<AdaptiveAnalysisPanel capture={capture} />);
    await screen.findByRole("progressbar", { name: "Saved adaptive analysis checkpoints" });
    expect(screen.getByText(/not a live-worker status/)).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
    if (state === "not_started") expect(screen.getByText(/does not start or queue/)).toBeInTheDocument();
    if (state === "partial") expect(screen.getByText(/full numerical contents are verified when/)).toBeInTheDocument();
    if (state === "metrics_complete") expect(screen.getByText(/figures have not been published/)).toBeInTheDocument();
    if (state === "figures_ready") {
      expect(screen.getAllByRole("img")).toHaveLength(3);
      expect(screen.getByText(/Marker opacity does not encode signal strength/)).toBeInTheDocument();
      expect(screen.getByText(/exceeded the configured output bound/)).toBeInTheDocument();
      const link = screen.getByRole("link", { name: "Open retained channel coverage PNG" });
      expect(link.getAttribute("href")).toContain("binding_sha256=sha256%3A");
      const image = screen.getByRole("img", { name: "Retained channel coverage" });
      fireEvent.error(image);
      expect(screen.getByRole("alert")).toHaveTextContent("figure could not be loaded");
    } else expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("distinguishes unsupported analysis from corruption", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    const view = render(<AdaptiveAnalysisPanel capture={capture} />);
    await screen.findByText(/It is not queued here/);
    view.unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 409)));
    render(<AdaptiveAnalysisPanel capture={capture} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("409");
  });

  it.each(["source", "stride", "integer-score", "count", "live-worker", "missing-figure", "external-figure", "wrong-metrics", "rounded-epoch", "receiver"])("rejects invalid %s evidence", async fault => {
    const value = analysisFixture();
    if (fault === "source") value.input_manifest_sha256 = sha("9");
    if (fault === "stride") value.configuration.probe_stride_ms = 10;
    if (fault === "integer-score") Object.assign(value.configuration, { decision_score: "integer" });
    if (fault === "count") value.checkpoint_visits--;
    if (fault === "live-worker") Object.assign(value, { worker_activity: "running" });
    if (fault === "missing-figure") value.overview!.artifacts.pop();
    if (fault === "external-figure") Object.assign(value.overview!.artifacts[0], { name: "https://untrusted.example/image.png" });
    if (fault === "wrong-metrics") value.overview!.metrics_manifest_sha256 = sha("9");
    if (fault === "rounded-epoch") Object.assign(value.overview!, { finalized_utc_ns: Number(value.overview!.finalized_utc_ns) });
    if (fault === "receiver") Object.assign(value.configuration, { receiver_ids: [false, true] });
    vi.stubGlobal("fetch", analysisFetch(value));
    await expect(getAdaptiveAnalysis(capture)).rejects.toThrow();
  });

  it("does not overlap polls and aborts on unmount", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<AdaptiveAnalysisPanel capture={capture} />);
    await act(async () => { vi.advanceTimersByTime(60000); });
    expect(fetcher).toHaveBeenCalledTimes(3);
    view.unmount();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it("ignores late results for a previously selected capture", async () => {
    let finish: (value: Response) => void = () => {};
    const old = new Promise<Response>(resolve => { finish = resolve; });
    vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(old).mockResolvedValue(respond(null, 404)));
    const view = render(<AdaptiveAnalysisPanel capture={capture} />);
    view.rerender(<AdaptiveAnalysisPanel capture={{ ...capture, session_id: "new" }} />);
    await screen.findByText(/It is not queued here/);
    await act(async () => { finish(respond(analysisFixture())); });
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("constructs only local digest-bound URLs", () => {
    const status = analysisFixture();
    expect(adaptiveFigureUrl(status, status.overview!.artifacts[0])).toMatch(/^\/api\/v1\/scanner\/adaptive-sessions\/adaptive-test\/analysis\/coverage\.png\?/);
    expect(adaptiveFigureUrl(status, status.overview!.artifacts[0])).toContain("probe_stride_ms=120");
  });

  it("keeps dense results explicitly separate from automatic overview sampling", async () => {
    const dense = analysisFixture();
    dense.configuration.probe_stride_ms = 10;
    dense.binding_sha256 = sha("1");
    dense.overview!.binding_sha256 = dense.binding_sha256;
    const fetcher = vi.fn((url: string) => Promise.resolve(
      url.includes("dual-rx-phase") ? respond(null, 404)
        : respond(url.includes("probe_stride_ms=10") ? dense : analysisFixture()),
    ));
    vi.stubGlobal("fetch", fetcher);
    render(<AdaptiveAnalysisPanel capture={capture} />);
    await screen.findByRole("img", { name: "Fractional GLRT response" });
    expect(fetcher.mock.calls[0][0]).toContain("probe_stride_ms=120");
    expect(screen.getByText(/20 ms probes \/ 120 ms stride/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Analysis sampling" }), { target: { value: "10" } });
    await screen.findByText(/20 ms probes \/ 10 ms stride/);
    const denseAnalysisCall = fetcher.mock.calls.find(call =>
      !String(call[0]).includes("dual-rx-phase") && String(call[0]).includes("probe_stride_ms=10")
    );
    expect(denseAnalysisCall?.[0]).toContain("probe_stride_ms=10");
    expect(screen.getByText(/not scheduled automatically/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open fractional glrt response PNG" }).getAttribute("href")).toContain("probe_stride_ms=10");
  });
});
