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
      const payload = path === "/api/v1/qualification/campaigns" ? campaignList
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

  it("renders searchable TEST evidence and no operational controls", async () => {
    render(<App />);
    expect(screen.getByText("Observation Console")).toBeInTheDocument();
    expect(screen.getByText("Read only")).toBeInTheDocument();
    await screen.findAllByText("TEST pilot window");
    expect(await screen.findByText("Known pilot candidate")).toBeInTheDocument();
    expect(screen.getAllByText("88.0%")).toHaveLength(2);
    expect(screen.getAllByText("Scientific confidence")).toHaveLength(2);
    expect(screen.getAllByText("Compute tier")).toHaveLength(2);
    expect(screen.getByText("candidate-1")).toBeInTheDocument();
    expect(screen.getByLabelText("Analysis stream-a")).toHaveTextContent("radio-test");
    expect(screen.getByLabelText("Analysis stream-b")).toHaveTextContent("radio-test-b");
    expect(screen.getByLabelText("Analysis stream-b")).toHaveTextContent("No candidate on stream-b");
    expect(screen.getAllByLabelText(/Waterfall stream-/)).toHaveLength(2);
    expect(screen.getAllByText("Baseband CFO offset").length).toBeGreaterThan(0);
    expect(screen.getByText("Search residual CFO")).toBeInTheDocument();
    expect(screen.getAllByText("Tuned-domain signal frequency").length).toBeGreaterThan(0);
    expect(screen.getByText("Fine CFO refinement")).toBeInTheDocument();
    expect(await screen.findAllByLabelText("Candidate overlay plot")).toHaveLength(2);
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

  it("shows twenty candidates initially and scales overlay seconds and CFO on real axes", async () => {
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
      } : url.includes("/status") ? status : url.includes("test-session") ? largeDetail : summary;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));

    render(<App />);
    expect(await screen.findByText("1–20 of 25")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Inspect candidate/ })).toHaveLength(20);
    expect(screen.getByLabelText("Selected candidate detail")).toHaveTextContent("candidate-25");
    expect(screen.getAllByText("Not run / no published result")).toHaveLength(2);
    expect(screen.getByText("Published for current run")).toBeInTheDocument();
    expect(screen.getByLabelText("Standard stage completion matrix")).toHaveTextContent("sparse-survey");
    expect(screen.getByLabelText("Standard stage completion matrix")).toHaveTextContent("insufficient data");
    expect(screen.getAllByLabelText("Candidate accounting")[0]).toHaveTextContent("25 retained here");

    fireEvent.change(screen.getByLabelText("Filter candidates by receiver"), { target: { value: "1" } });
    expect(screen.getAllByRole("button", { name: /Inspect candidate/ })).toHaveLength(12);
    fireEvent.change(screen.getByLabelText("Sort candidates"), { target: { value: "time" } });
    expect(screen.getByLabelText("Selected candidate detail")).toHaveTextContent("candidate-02");

    const overlay = await screen.findByLabelText("Candidate overlay plot");
    const point = Array.from(overlay.querySelectorAll("i")).find((marker) => marker.title.startsWith("1.513484s"));
    expect(point).toBeDefined();
    expect(Number.parseFloat(point!.style.left)).toBeCloseTo(1.513484 / 60 * 100, 5);
    expect(Number.parseFloat(point!.style.bottom)).toBeCloseTo((253_443.36 - 200_000) / 100_000 * 100, 5);
    const waterfallPoint = screen.getAllByLabelText("Waterfall plot")[0].querySelector('circle[cy]');
    expect(Number.parseFloat(waterfallPoint!.getAttribute("cx")!)).toBeCloseTo(0, 5);
    expect(Number.parseFloat(waterfallPoint!.getAttribute("cy")!)).toBeCloseTo(220, 5);
    expect(screen.getAllByLabelText("Time axis 0 to 60 seconds").length).toBeGreaterThanOrEqual(2);
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
