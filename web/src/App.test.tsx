import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type {
  QualificationCampaignDetailV1,
  QualificationCampaignListV1,
  RecordingDetailV1,
  RecordingSearchResponseV1,
  SystemStatusV1,
} from "./contracts.generated";

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

const activeQueue = {
  schema_version: 1 as const,
  generated_at: "2026-08-20T03:00:00Z",
  returned_count: 2,
  truncated: false,
  items: [
    {
      schema_version: 1 as const, job_id: 101, run_id: "run-live", session_id: "capture-live",
      pipeline_release_id: "a".repeat(40), stage_key: "path-pilot-scan",
      description: "Search GLRT64, Symbolwise, and Anchor-8 pilot responses", state: "leased" as const,
      resource_class: "heavy" as const, scope_kind: "receiver_path" as const,
      stream_id: "stream-0", radio_id: "radio-a", receiver_id: 1, worker_id: "worker-2",
      created_at: "2026-08-20T02:59:00Z", updated_at: "2026-08-20T03:00:00Z",
    },
    {
      schema_version: 1 as const, job_id: 102, run_id: "run-live", session_id: "capture-live",
      pipeline_release_id: "a".repeat(40), stage_key: "paired-scientific-report",
      description: "Align both radios on the shared time domain", state: "pending" as const,
      resource_class: "cpu" as const, scope_kind: "paired" as const,
      stream_id: null, radio_id: null, receiver_id: null, worker_id: null,
      created_at: "2026-08-20T02:59:00Z", updated_at: "2026-08-20T02:59:00Z",
    },
  ],
};

const acquisitionQueue = {
  schema_version: 1 as const,
  generated_at: "2026-08-20T03:00:00Z",
  returned_count: 2,
  truncated: false,
  items: [
    {
      schema_version: 1 as const, operation_id: 201,
      operation_key: "scheduled-dwell:live-60s:2026-08-20T03:00:00+00:00",
      kind: "scheduled_recording" as const, state: "leased" as const,
      profile_name: "live-60s", radio_ids: ["radio-a", "radio-b"],
      worker_id: "capture-supervisor:station:123", scheduled_for: "2026-08-20T03:00:00Z",
      attempt_count: 1, error: null,
    },
    {
      schema_version: 1 as const, operation_id: 202,
      operation_key: "scan-after:scheduled-dwell:live-60s:2026-08-20T03:00:00+00:00",
      kind: "scanner_sweep" as const, state: "pending" as const,
      profile_name: null, radio_ids: [], worker_id: null,
      scheduled_for: "2026-08-20T03:01:00Z", attempt_count: 0, error: null,
    },
  ],
};

const scannerReport = {
  schema_version: 1 as const,
  kind: "starlink_scanner_report" as const,
  scan_id: "scan-2d0e49b94b3e4cdf",
  radio_id: "radio_pluto_5d4d",
  radio_serial: "serial-5d4d",
  capture_elapsed_ms: 1557.04,
  analysis_elapsed_ms: 16799.62,
  candidate_only: true as const,
  payload_decoded: false as const,
  configuration: { dwell_ms: 80, gain_mode: "manual", gain_db: 40, glrt64_margin_gate: 0.025 },
  results: Array.from({ length: 8 }, (_, index) => ({
    target: {
      channel: Math.floor(index / 2) + 1,
      edge: index % 2 === 0 ? "lower" as const : "upper" as const,
      rf_center_hz: 10_709_687_500 + index * 230_625_000,
      if_center_hz: 959_687_500 + index * 230_625_000,
    },
    decision: index < 6 ? "active" as const : "no_detection" as const,
    requested_if_center_hz: 959_687_500 + index * 230_625_000,
    actual_if_center_hz: 959_687_500 + index * 230_625_000,
    best_margin: index < 6 ? 0.25 : null,
    first_detection: index < 6 ? { receiver_id: index % 2, probe_start_ms: 20, tracking_cfo_hz: 125_000, margin: 0.25 } : null,
    reason: index < 6 ? "GLRT64 candidate evidence" : "no GLRT64 hit",
  })),
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
  stream_analyses: [],
  stage_matrix: null,
  provenance: { analysis_run_id: "run-test", pipeline_release: "analysis-test", generated_at: "2026-08-19T00:00:01Z", config_digest: "b".repeat(64), recording_digest: "a".repeat(64), limitation_codes: ["candidate-only"] },
  products: ["waterfall", "overlays"].map((kind) => ({
    schema_version: 1 as const, product_id: `product-${kind}`, session_id: "test-session",
    analysis_run_id: "run-test", kind: kind as "waterfall" | "overlays", status: "complete" as const,
    content_type: "application/json" as const, artifact_path: `/srv/bulk/${kind}.json`,
    byte_count: 100, sha256: "d".repeat(64), coverage: analysis.coverage, summary: {},
  })),
};

const pairedDetail: RecordingDetailV1 = {
  ...detail,
  radios: [
    detail.radios[0],
    { ...detail.radios[0], radio_id: "radio-test-b", serial: "serial-test-b" },
  ],
  products: ["stream-a", "stream-b"].flatMap((scope) =>
    ["waterfall", "overlays"].map((kind) => ({
      ...detail.products[0],
      product_id: `product-${kind}-${scope}`,
      kind: kind as "waterfall" | "overlays",
      artifact_path: `/srv/bulk/${kind}-${scope}.json`,
      summary: { scope_key: scope },
    })),
  ),
  stream_analyses: [
    {
      scope_key: "stream-a", radio_id: "radio-test", receiver_labels: ["rx0", "rx1"],
      is_primary: true, detection: detail.detection, whole_dwell: detail.whole_dwell,
      qam: detail.qam, doppler: detail.doppler,
    },
    {
      scope_key: "stream-b", radio_id: "radio-test-b", receiver_labels: ["rx0", "rx1"],
      is_primary: false,
      detection: { ...detail.detection, state: "none", known_pilot_candidate: false, qin_score: null, control_score: null, reason: "No candidate on stream-b" },
      whole_dwell: { ...detail.whole_dwell, candidate_count: 0, returned_candidate_count: 0, candidates: [], confidence: "insufficient", confidence_reason: "No candidate on stream-b" },
      qam: { ...detail.qam, state: "no_result", combined_accuracy: null, receiver_accuracy: [], rms_evm: null, frame_count: 0, receiver_metrics: [] },
      doppler: { ...detail.doppler, state: "no_result", slope_hz_per_s: null, baseband_cfo_at_reference_hz: null, tuned_signal_frequency_at_reference_hz: null, frequency_span_hz: null, residual_rms_hz: null, point_count: 0, motion_class: "indeterminate" },
    },
  ],
};

const pairedRadioSetup = {
  schema_version: 2 as const,
  session_id: "test-session",
  radios: [
    {
      schema_version: 2 as const, radio_id: "radio-test", radio_index: 0,
      applied_if_center_frequency_hz: 1_440_312_500,
      target_rf_center_frequency_hz: 11_190_312_500,
      applied_bandwidth_hz: 2_500_000, applied_sample_rate_hz: 2_500_000,
      gain_mode: "slow_attack" as const,
      starlink_channel: "ch2", starlink_edge: "upper" as const,
      firmware_version: "0.39-radio-a",
    },
    {
      schema_version: 2 as const, radio_id: "radio-test-b", radio_index: 1,
      applied_if_center_frequency_hz: 1_209_687_500,
      target_rf_center_frequency_hz: 10_959_687_500,
      applied_bandwidth_hz: 2_500_000, applied_sample_rate_hz: 2_500_000,
      gain_mode: "manual" as const,
      starlink_channel: "ch2", starlink_edge: "lower" as const,
      firmware_version: null,
    },
  ],
};

const status: SystemStatusV1 = {
  schema_version: 1,
  generated_at: "2026-08-19T00:00:00Z",
  storage: { total_bytes: 100, used_bytes: 26, used_fraction: .26, retention_high_watermark: .7, retention_low_watermark: .65, admission_state: "open" },
  backlog: { queued: 3, running: 2, failed: 0, oldest_queued_seconds: 4 },
  api_mode: "read_only",
};

const campaignItem = {
  schema_version: 1 as const,
  campaign_id: "wp11-campaign-a",
  authority_status: "authoritative_sealed" as const,
  result_status: "pass" as const,
  reason: "All four predeclared strata passed recovery and QAM gates.",
  mathematical_eligible: true,
  production_accepted: true,
  expected_session_count: 30 as const,
  observed_session_count: 30,
  expected_stream_count: 40 as const,
  observed_stream_count: 40,
  sealed_at: "2026-08-19T02:00:00Z",
  candidate_only: true as const,
  specificity_claimed: false as const,
  attribution_claimed: false as const,
  payload_decoded: false as const,
};

const campaignList: QualificationCampaignListV1 = {
  schema_version: 1,
  items: [campaignItem],
  total: 1,
  next_cursor: null,
};
const campaignDetail: QualificationCampaignDetailV1 = {
  ...campaignItem,
  pipeline_release_ids: ["wp11-release-a"],
  capture: { logical_uri: "qualification://capture/accepted.json", digest: `sha256:${"a".repeat(64)}` },
  outer_seal: {
    logical_uri: "qualification://campaign/wp11-campaign-a/seal.json",
    digest: `sha256:${"b".repeat(64)}`,
  },
  outer_sealed_utc_ns: 1_777_777_777_000_000_000,
  current_release_evidence_digest: `sha256:${"c".repeat(64)}`,
  strata: ["independent-a", "independent-b", "paired-a", "paired-b"].map((stratum_id) => ({
    stratum_id,
    status: "pass" as const,
    reason: "Recovery lower bound and QAM noninferiority passed.",
    expected_session_count: 10,
    observed_session_count: 10,
    reference_positive_count: 80,
    associated_reference_positive_count: 76,
    recovery: {
      successes: 76, trials: 80, point_estimate: .95, confidence_level: .95,
      wilson_lower_bound: .88, clopper_pearson_lower_bound: .86,
      method: "wilson-and-clopper-pearson-one-sided" as const,
    },
    qam: {
      reference_positive_count: 70, native_recovery_count: 69,
      mean_accuracy_difference: .012, accuracy_difference_lower_bound: -.018,
      interval_method: "paired-student-t-one-sided-95", noninferiority_passed: true,
    },
  })),
  calibrations: [{
    frequency_calibration_id: 17, calibration_id: "calibration-radio-a-rx1",
    radio_id: "radio-a", radio_serial: "serial-a", receiver_id: 1,
    physical_receiver_id: "radio-a-rx1", hardware_epoch_id: "epoch-a",
    center_hz: -4192.5, uncertainty_lower_hz: -8298.5, uncertainty_upper_hz: 8298.5,
    valid_from_utc_ns: 1_777_000_000_000_000_000, valid_until_utc_ns: null,
    method: "trusted-wp11-empirical-search-prior-v1",
    evidence_uri: "qualification://frequency-calibration/calibration-radio-a-rx1/evidence.json",
    evidence_digest: `sha256:${"d".repeat(64)}`, session_count: 30, stream_count: 20,
  }],
};

describe("Observation Console", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = new URL(url, "http://localhost").pathname;
      const payload = path === "/api/v2/control/status" ? {
        schema_version: 2,
        standard_reprocess_enabled: true,
        research_reprocess_enabled: true,
      } : path.endsWith("/reprocess") ? {
        schema_version: 1,
        session_id: "test-session",
        run_id: `reprocess-${"a".repeat(32)}`,
        pipeline_release_id: "a".repeat(40),
        previous_current_run_id: "run-test",
        queued_job_count: 7,
        state: "queued",
      } : path.endsWith("/radio-setup") ? pairedRadioSetup
        : path === "/api/v1/scanner/reports" ? {
          schema_version: 1, cursor: 0, limit: 20, total: 2, next_cursor: null,
          items: [
            { schema_version: 1, scanned_at: "2026-08-21T02:00:00Z", report: scannerReport },
            { schema_version: 1, scanned_at: "2026-08-21T01:00:00Z", report: { ...scannerReport, scan_id: "scan-older" } },
          ],
        }
        : path === "/api/v1/acquisition-queue" ? acquisitionQueue
        : path === "/api/v1/queue" ? activeQueue
        : path === "/api/v1/qualification/campaigns" ? campaignList
        : url.includes("/api/v1/qualification/campaigns/wp11-campaign-a") ? campaignDetail
        : url.includes("/content") ? {
        schema_version: 1, product_id: url.includes("overlays") ? "product-overlays" : "product-waterfall",
        analysis_run_id: "run-test", kind: url.includes("overlays") ? "overlays" : "waterfall",
        source_point_count: 1, returned_point_count: 1, truncated: false,
        points: [{ x: .002, y: 225000, value: .38 }], metadata: { run_id: "run-test", frequency_unit: "Hz" },
      } : url.includes("/status") ? status : url.includes("test-session") ? pairedDetail : summary;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("queues a new analysis while retaining the current result", async () => {
    render(<App />);
    expect(screen.getByText("Observation Console")).toBeInTheDocument();
    expect(await screen.findByText("Operator controls")).toBeInTheDocument();
    expect(screen.getByText("Current time")).toBeInTheDocument();
    expect(await screen.findByText(/since last recording/)).toBeInTheDocument();
    await screen.findAllByText("TEST pilot window");
    expect(await screen.findByText("Acquisition geometry")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Radio 0 captured setup" })).toHaveTextContent("1,440.3125 MHz");
    expect(screen.getByRole("table", { name: "Radio 0 captured setup" })).toHaveTextContent("11,190.3125 MHz");
    expect(screen.getByRole("table", { name: "Radio 0 captured setup" })).toHaveTextContent("Channel 2 · upper");
    expect(screen.getByRole("table", { name: "Radio 0 captured setup" })).toHaveTextContent("Slow-attack AGC");
    expect(screen.getByRole("table", { name: "Radio 0 captured setup" })).toHaveTextContent("0.39-radio-a");
    expect(screen.getByRole("table", { name: "Radio 1 captured setup" })).toHaveTextContent("1,209.6875 MHz");
    expect(screen.getByRole("table", { name: "Radio 1 captured setup" })).toHaveTextContent("10,959.6875 MHz");
    expect(screen.queryByText("Power & quality")).not.toBeInTheDocument();
    expect(screen.queryByText("Synchronized stream waterfalls")).not.toBeInTheDocument();
    expect(screen.queryByText("Whole-dwell candidate evidence")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Re-run analysis" }));
    expect(await screen.findByText(/7 jobs queued/)).toHaveTextContent(
      "The current output remains visible until this run seals",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/v2/control/recordings/test-session/reprocess",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByRole("button", { name: /purge|start capture/i })).not.toBeInTheDocument();
  });

  it("shows exactly one captured setup table for a single-radio recording", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = new URL(url, "http://localhost").pathname;
      const payload = path === "/api/v2/control/status"
        ? { schema_version: 2, standard_reprocess_enabled: true, research_reprocess_enabled: true }
        : path.endsWith("/radio-setup")
          ? { ...pairedRadioSetup, radios: [pairedRadioSetup.radios[0]] }
          : url.includes("/status")
            ? status
            : url.includes("test-session")
              ? detail
              : summary;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));

    render(<App />);
    expect(await screen.findByRole("table", { name: "Radio 0 captured setup" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Radio 1 captured setup" })).not.toBeInTheDocument();
  });

  it("sends filters through the read query", async () => {
    render(<App />);
    const search = screen.getByRole("searchbox", { name: "Search recordings" });
    fireEvent.change(search, { target: { value: "pilot" } });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining("query=pilot"), expect.anything());
    });
  });

  it("shows bounded active and queued work with recording and radio identity", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Queue" }));
    expect(await screen.findByRole("heading", { name: "Active and queued jobs" })).toBeInTheDocument();
    expect(screen.getAllByText("1 active · 1 queued")).toHaveLength(2);
    expect(screen.getAllByText("capture-live")).toHaveLength(2);
    expect(screen.getByRole("table", { name: "Acquisition operations" })).toHaveTextContent("scheduled_recording");
    expect(screen.getByRole("table", { name: "Acquisition operations" })).toHaveTextContent("scanner_sweep");
    expect(screen.getByText("radio-a")).toBeInTheDocument();
    expect(screen.getByText("stream-0 · RX1")).toBeInTheDocument();
    expect(screen.getByText("Both radios")).toBeInTheDocument();
    expect(screen.getByText("Search GLRT64, Symbolwise, and Anchor-8 pilot responses")).toBeInTheDocument();
  });

  it("shows scanner history and selects an exact report", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Scanner" }));
    expect(await screen.findByRole("heading", { name: "Starlink channel scans" })).toBeInTheDocument();
    expect(screen.getByText("2 scans")).toBeInTheDocument();
    expect(screen.getAllByText("scan-2d0e49b94b3e4cdf")).toHaveLength(2);
    expect(screen.getByRole("table", { name: "Scanner history" })).toHaveTextContent("scan-older");
    expect(screen.getByRole("table", { name: "Selected scanner results" })).toHaveTextContent("CH4");
    expect(screen.getByRole("table", { name: "Selected scanner results" })).toHaveTextContent("125,000 Hz");
    expect(screen.getByText("Candidate-only GLRT64; no payload decoded")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /8\/21\/2026/ })[1]);
    expect(screen.getByLabelText("Scanner summary")).toHaveTextContent("scan-older");
  });

  it("keeps current-run stage completion collapsed after removing legacy scientific panels", async () => {
    const template = detail.whole_dwell.candidates[0];
    const candidates = Array.from({ length: 25 }, (_, index) => ({
      ...template,
      candidate_id: `candidate-${String(index + 1).padStart(2, "0")}`,
      receiver_key: String(index % 2),
      time_s: index === 24 ? 1.513484 : index * 2,
      baseband_cfo_hz: index === 24 ? 253_443.36 : 200_000 + index * 4_000,
      margin: index === 24 ? .999 : index / 100,
    }));
    const largeDetail: RecordingDetailV1 = {
      ...detail,
      duration_seconds: 60,
      profile: { ...detail.profile, dwell_seconds: 60 },
      whole_dwell: {
        ...detail.whole_dwell,
        candidate_count: 256,
        returned_candidate_count: candidates.length,
        candidate_lineage_truncated: true,
        candidates,
      },
      stage_matrix: {
        analysis_run_id: "run-test",
        source_stage_count: 2,
        returned_stage_count: 2,
        truncated: false,
        stages: [
          { job_id: 1, stage_key: "sparse-survey", scope_key: "primary", state: "succeeded", outcome: "complete" },
          { job_id: 2, stage_key: "qam-handoff", scope_key: "primary", state: "failed", outcome: "insufficient_data" },
        ],
      },
      products: detail.products.map((product) => ({ ...product, summary: { scope_key: "primary" } })),
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = new URL(url, "http://localhost").pathname;
      const payload = url.includes("/content") ? {
        schema_version: 1,
        product_id: url.includes("overlays") ? "product-overlays" : "product-waterfall",
        analysis_run_id: "run-test",
        kind: url.includes("overlays") ? "overlays" : "waterfall",
        source_point_count: 3,
        returned_point_count: 3,
        truncated: false,
        points: [
          { x: 0, y: 200_000, value: .1 },
          { x: 1.513484, y: 253_443.36, value: .999 },
          { x: 60, y: 300_000, value: .2 },
        ],
        metadata: { frequency_unit: "Hz" },
      } : path.endsWith("/radio-setup") ? pairedRadioSetup
        : url.includes("/status") ? status : url.includes("test-session") ? largeDetail : summary;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));

    render(<App />);
    expect(await screen.findByText("Acquisition geometry")).toBeInTheDocument();
    const stageMatrix = screen.getByLabelText("Standard stage completion matrix");
    expect(stageMatrix).not.toHaveAttribute("open");
    expect(stageMatrix).toHaveTextContent("sparse-survey");
    expect(stageMatrix).toHaveTextContent("insufficient data");
    expect(screen.queryByLabelText("Candidate accounting")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Candidate overlay plot")).not.toBeInTheDocument();
  });

  it("renders bounded authoritative WP11 evidence with permanent limitations", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "WP11 qualification" }));
    expect(await screen.findByText("wp11-campaign-a")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Recovery and confidence" })).toBeInTheDocument();
    expect(screen.getByLabelText("Permanent scientific limitation")).toHaveTextContent(
      "do not establish Starlink specificity, satellite attribution, or payload decoding",
    );
    expect(screen.getByText("production accepted")).toBeInTheDocument();
    expect(screen.getAllByText("QAM noninferiority")).toHaveLength(4);
    expect(screen.getByText("calibration-radio-a-rx1")).toBeInTheDocument();
    expect(screen.getByText("-8,298.5 to 8,298.5 Hz")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reprocess|purge|start capture/i })).not.toBeInTheDocument();
  });

  it("pages through more than ten authoritative campaigns", async () => {
    const items = Array.from({ length: 12 }, (_, index) => ({
      ...campaignItem,
      campaign_id: `wp11-campaign-${String(index + 1).padStart(2, "0")}`,
    }));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      let payload: unknown;
      if (url.pathname === "/api/v1/qualification/campaigns") {
        const cursor = Number(url.searchParams.get("cursor") ?? 0);
        payload = {
          schema_version: 1,
          items: items.slice(cursor, cursor + 10),
          total: 12,
          next_cursor: cursor === 0 ? 10 : null,
        } satisfies QualificationCampaignListV1;
      } else if (url.pathname.startsWith("/api/v1/qualification/campaigns/")) {
        payload = campaignDetail;
      } else if (url.pathname.includes("/status")) {
        payload = status;
      } else {
        payload = summary;
      }
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "WP11 qualification" }));
    expect(await screen.findByText("10 of 12 authoritative")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more campaigns (2 remaining)" }));
    expect(await screen.findByText("wp11-campaign-12")).toBeInTheDocument();
    expect(screen.getByText("12 of 12 authoritative")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Load more campaigns/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("cursor=10&limit=10"),
      expect.anything(),
    );
  });
});
