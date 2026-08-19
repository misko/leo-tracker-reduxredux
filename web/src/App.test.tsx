import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { RecordingDetailV1, RecordingSearchResponseV1, SystemStatusV1 } from "./contracts.generated";

const analysis = {
  state: "complete" as const,
  current_run: {
    run_id: "run-test",
    pipeline_release: "analysis-test",
    state: "complete" as const,
    started_at: "2026-08-19T00:00:00Z",
    finished_at: "2026-08-19T00:00:01Z",
    is_current: true as const,
  },
  coverage: {
    analyzed_fraction: 1,
    analyzed_seconds: 0.01,
    dwell_seconds: 0.01,
    description: "complete",
  },
  failure_reason: null,
  no_result_reason: null,
  product_count: 0,
};

const summary: RecordingSearchResponseV1 = {
  schema_version: 1,
  total: 1,
  next_cursor: null,
  items: [{
    schema_version: 1,
    session_id: "test-session",
    title: "TEST pilot window",
    started_at: "2026-08-19T00:00:00Z",
    duration_seconds: 0.01,
    source_type: "TEST",
    tags: ["TEST"],
    hold: { held: true, reason: "TEST fixture" },
    capture_health: "complete",
    storage_state: "available",
    profile_name: "Test profile",
    radio_count: 1,
    analysis,
  }],
};

const detail: RecordingDetailV1 = {
  ...summary.items[0],
  profile: {
    profile_id: "profile-test",
    name: "Test profile",
    revision: 1,
    sample_rate_hz: 2_500_000,
    bandwidth_hz: 2_500_000,
    dwell_seconds: 0.01,
    center_frequency_hz: 1_709_687_500,
    receiver_count_per_radio: 2,
  },
  radios: [{
    radio_id: "radio-test",
    serial: "serial-test",
    receiver_labels: ["rx0", "rx1"],
    state: "complete",
    captured_samples: 25_000,
    sample_rate_hz: 2_500_000,
    gain_db: [44, 44],
    raw_path: "/srv/bulk/test.ci16",
    continuity_gaps: 0,
    clipped_samples: 0,
  }],
  synchronization: {
    mode: "none",
    grade: "not_requested",
    start_skew_ms: null,
    skew_uncertainty_ms: null,
    overlap_seconds: null,
    overlap_fraction: null,
    timing_basis: "imported",
    phase_coherent: false,
  },
  paths: {
    recording_root: "/srv/bulk/test",
    manifest_path: "/srv/bulk/test/manifest.json",
    analysis_root: "/srv/bulk/test/analysis",
  },
  quality: { state: "complete", clipped_fraction: 0, constant_iq_refills: 0, continuity_gaps: 0, note: "Healthy" },
  power: [],
  detection: { state: "candidate", known_pilot_candidate: true, calibrated_detection: false, qin_score: .4, control_score: .02, reason: "Candidate only" },
  whole_dwell: {
    analysis_run_id: "run-test",
    compute_tier: "standard",
    confidence: "candidate",
    confidence_reason: "Uncalibrated candidate evidence",
    candidate_count: 1,
    returned_candidate_count: 1,
    candidate_lineage_truncated: false,
    candidate_coverage: {
      scheduled_windows: 10, complete_windows: 8, searched_receiver_windows: 16,
      searched_samples: 20_000, searched_time_fraction: .8,
      residual_cfo_min_hz: -400_000, residual_cfo_max_hz: 400_000,
      survey_config_digest: "b".repeat(64),
    },
    candidates: [{
      candidate_id: "candidate-1", receiver_key: "0", time_s: .002,
      absolute_epoch_sample: 5000, search_residual_cfo_hz: 225_000,
      baseband_cfo_hz: 225_000, receiver_tuned_center_hz: 1_709_687_500,
      tuned_signal_frequency_hz: 1_709_912_500, verify_score: .4, control_score: .02,
      margin: .38, rank_within_search: 0, track_id: "track-1",
      calibration_digest: "c".repeat(64), parent_survey_config_digest: "b".repeat(64),
    }],
    controls: {
      state: "complete", thresholds_calibrated: false, specificity_claimed: false,
      passed_candidate_count: 1, best_held_out_margin: .38, best_surrogate_margin: .35,
      rejection_reasons: ["specificity uncalibrated"], reason: "Research gate passed",
    },
  },
  qam: {
    state: "complete", combined_accuracy: .88, receiver_accuracy: [.75, .8],
    rms_evm: .63, frame_count: 6, known_symbols_only: true,
    receiver_metrics: [{
      receiver_key: "0", candidate_epoch_sample: 2063, baseband_cfo_hz: 364_150.85,
      residual_cfo_refinement_hz: 5.79, receiver_tuned_center_hz: 1_709_687_500,
      tuned_signal_frequency_hz: 1_710_051_650.85, accuracy: .75, rms_evm: .7,
      frame_count: 6, noise_variance: .02,
    }],
  },
  doppler: {
    state: "partial", slope_hz_per_s: -4000, baseband_cfo_at_reference_hz: 225_000,
    receiver_tuned_center_hz: 1_709_687_500, tuned_signal_frequency_at_reference_hz: 1_709_912_500,
    frequency_span_hz: 80000,
    correlation: .99, residual_rms_hz: 300, point_count: 7, motion_class: "dynamic",
    confidence: "candidate", tle_candidate: null, association_status: "unavailable",
  },
  provenance: { analysis_run_id: "run-test", pipeline_release: "analysis-test", generated_at: "2026-08-19T00:00:01Z", config_digest: "b".repeat(64), recording_digest: "a".repeat(64), limitation_codes: ["candidate-only"] },
  products: ["waterfall", "overlays"].map((kind) => ({
    schema_version: 1 as const, product_id: `product-${kind}`, session_id: "test-session",
    analysis_run_id: "run-test", kind: kind as "waterfall" | "overlays", status: "complete" as const,
    content_type: "application/json" as const, artifact_path: `/srv/bulk/${kind}.json`,
    byte_count: 100, sha256: "d".repeat(64), coverage: analysis.coverage, summary: {},
  })),
};

const status: SystemStatusV1 = {
  schema_version: 1,
  generated_at: "2026-08-19T00:00:00Z",
  storage: { total_bytes: 100, used_bytes: 26, used_fraction: .26, retention_high_watermark: .7, retention_low_watermark: .65, admission_state: "open" },
  backlog: { queued: 3, running: 2, failed: 0, oldest_queued_seconds: 4 },
  api_mode: "read_only",
};

describe("Observation Console", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/content") ? {
        schema_version: 1, product_id: url.includes("overlays") ? "product-overlays" : "product-waterfall",
        analysis_run_id: "run-test", kind: url.includes("overlays") ? "overlays" : "waterfall",
        source_point_count: 1, returned_point_count: 1, truncated: false,
        points: [{ x: .002, y: 225000, value: .38 }], metadata: { run_id: "run-test", frequency_unit: "Hz" },
      } : url.includes("/status") ? status : url.includes("test-session") ? detail : summary;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders searchable TEST evidence and no operational controls", async () => {
    render(<App />);
    expect(screen.getByText("Observation Console")).toBeInTheDocument();
    expect(screen.getByText("Read only")).toBeInTheDocument();
    await screen.findAllByText("TEST pilot window");
    expect(await screen.findByText("Known pilot candidate")).toBeInTheDocument();
    expect(screen.getAllByText("88.0%")).toHaveLength(2);
    expect(screen.getByText("Scientific confidence")).toBeInTheDocument();
    expect(screen.getByText("Compute tier")).toBeInTheDocument();
    expect(screen.getByText("candidate-1")).toBeInTheDocument();
    expect(screen.getAllByText("Baseband CFO offset").length).toBeGreaterThan(0);
    expect(screen.getByText("Search residual CFO")).toBeInTheDocument();
    expect(screen.getAllByText("Tuned-domain signal frequency").length).toBeGreaterThan(0);
    expect(screen.getByText("Fine CFO refinement")).toBeInTheDocument();
    expect(await screen.findByLabelText("Candidate overlay plot")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reprocess|purge|start capture/i })).not.toBeInTheDocument();
  });

  it("sends filters through the read query", async () => {
    render(<App />);
    const search = screen.getByRole("searchbox", { name: "Search recordings" });
    fireEvent.change(search, { target: { value: "pilot" } });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining("query=pilot"), expect.anything());
    });
  });
});
