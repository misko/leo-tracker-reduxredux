import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdaptiveAnalysisPanel } from "./AdaptiveAnalysisPanel";
import { adaptiveFigureUrl, getAdaptiveAnalysis } from "./adaptive-analysis-api";
import type { AdaptiveAnalysisStatus } from "./adaptive-analysis-api";
import { adaptiveDetailFixture } from "./adaptive-fixtures";

const capture = adaptiveDetailFixture().capture;
const respond = (value: unknown, status = 200) => ({ ok: status === 200, status, json: async () => value }) as Response;
const sha = (letter: string) => `sha256:${letter.repeat(64)}`;
export function analysisFixture(state: AdaptiveAnalysisStatus["state"] = "figures_ready"): AdaptiveAnalysisStatus {
  const complete = state === "figures_ready" || state === "metrics_complete";
  return {
    schema_version: 1, kind: "adaptive_hop_analysis_status", session_id: capture.session_id,
    input_manifest_sha256: capture.input_manifest_sha256, binding_sha256: sha("a"),
    configuration: { schema_version: 1, analyzer_id: "adaptive-hop-fractional-glrt64-cfo-v1", sample_rate_hz: capture.sample_rate_hz,
      valid_visit_ms: 120, probe_ms: 20, probe_stride_ms: 10, glrt64_margin_gate: .025, maximum_acquisition_candidates: 8,
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
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("adaptive analysis publication", () => {
  it.each(["not_started", "partial", "metrics_complete", "figures_ready"] as const)("shows %s without inventing live-worker status", async state => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(analysisFixture(state))));
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
    if (fault === "stride") value.configuration.probe_stride_ms = 120;
    if (fault === "integer-score") Object.assign(value.configuration, { decision_score: "integer" });
    if (fault === "count") value.checkpoint_visits--;
    if (fault === "live-worker") Object.assign(value, { worker_activity: "running" });
    if (fault === "missing-figure") value.overview!.artifacts.pop();
    if (fault === "external-figure") Object.assign(value.overview!.artifacts[0], { name: "https://untrusted.example/image.png" });
    if (fault === "wrong-metrics") value.overview!.metrics_manifest_sha256 = sha("9");
    if (fault === "rounded-epoch") Object.assign(value.overview!, { finalized_utc_ns: Number(value.overview!.finalized_utc_ns) });
    if (fault === "receiver") Object.assign(value.configuration, { receiver_ids: [false, true] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    await expect(getAdaptiveAnalysis(capture)).rejects.toThrow();
  });

  it("does not overlap polls and aborts on unmount", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<AdaptiveAnalysisPanel capture={capture} />);
    await act(async () => { vi.advanceTimersByTime(60000); });
    expect(fetcher).toHaveBeenCalledTimes(1);
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
  });
});
