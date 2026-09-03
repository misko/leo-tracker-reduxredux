import type {
  ProductContentV1,
  ActiveQueueV1,
  AcquisitionQueueV1,
  RecordingDetailV1,
  RecordingRadioSetupV2,
  RecordingSearchResponseV1,
  SystemStatusV1,
} from "./contracts.generated";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "GET", signal });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export interface CaptureControlStateV1 {
  schema_version: 1;
  generation: number;
  desired_state: "running" | "paused";
  observed_state: "running" | "pausing" | "paused";
  changed_utc_ns: number;
  operator_id: string;
  reason: string;
}

export function getCaptureControl(signal?: AbortSignal): Promise<CaptureControlStateV1> {
  return getJson<CaptureControlStateV1>("/api/v1/capture-control", signal);
}

export function stopCapture(): Promise<CaptureControlStateV1> {
  return postJson<CaptureControlStateV1>("/api/v1/capture-control/stop");
}

export function startCapture(): Promise<CaptureControlStateV1> {
  return postJson<CaptureControlStateV1>("/api/v1/capture-control/start");
}

export interface StandardReprocessResultV1 {
  schema_version: 1;
  session_id: string;
  run_id: string;
  pipeline_release_id: string;
  previous_current_run_id: string | null;
  queued_job_count: number;
  state: "queued";
}

export interface AnalysisControlStatusV2 {
  schema_version: 2;
  standard_reprocess_enabled: boolean;
  research_reprocess_enabled: boolean;
}

export interface ResearchReprocessResultV1 {
  schema_version: 1;
  pipeline_lane: "research";
  session_id: string;
  run_id: string;
  pipeline_release_id: string;
  previous_research_run_id: string | null;
  queued_job_count: number;
  scheduling_priority: "lower_than_standard";
  state: "queued";
}

export interface ScannerReportV1 {
  schema_version: 1;
  kind: "starlink_scanner_report";
  scan_id: string;
  radio_id: string;
  radio_serial: string;
  capture_elapsed_ms: number;
  analysis_elapsed_ms: number;
  candidate_only: true;
  payload_decoded: false;
  configuration: {
    dwell_ms: number;
    gain_mode: string;
    gain_db: number;
    glrt64_margin_gate: number;
  };
  results: Array<{
    target: { channel: number; edge: "lower" | "upper"; rf_center_hz: number; if_center_hz: number };
    decision: "active" | "no_detection" | "inconclusive";
    requested_if_center_hz: number;
    actual_if_center_hz: number | null;
    best_margin: number | null;
    first_detection: null | {
      receiver_id: number;
      probe_start_ms: number;
      tracking_cfo_hz: number;
      margin: number;
    };
    reason: string;
  }>;
}

export interface ScannerFrameContinuityEvidenceV1 {
  schema_version: 1;
  status: "attested" | "capture_failed";
  target_index: number;
  metadata_abi_version: number | null;
  stream_id: number | null;
  stream_generation: string | null;
  buffer_sequence: number | null;
  source_sequence: number | null;
  first_sample_sequence: number | null;
  last_sample_sequence_exclusive: number | null;
  device_sample_counter: number | null;
  device_sample_counter_end_exclusive: number | null;
  metadata_flags: number | null;
  sample_time_realtime_start_ns: number | null;
  sample_time_realtime_end_ns: number | null;
  sample_time_monotonic_start_ns: number | null;
  sample_time_monotonic_end_ns: number | null;
  sample_time_uncertainty_ns: number | null;
  kernel_buffers_requested: number | null;
  kernel_buffers_readback: number | null;
  reset_episode: number | null;
  missing_samples_before: number;
  overflow_observed: boolean;
  continuity_observable: boolean;
  within_frame_continuity: "proven_within_returned_buffer" | "unavailable_capture_failed";
  cross_frame_continuity: "not_applicable_retune_boundary";
  reason: string;
}

export type ScannerReportV2 = Omit<ScannerReportV1, "schema_version" | "kind" | "configuration"> & {
  schema_version: 2;
  kind: "starlink_scanner_report_v2";
  continuity_observable: true;
  retune_boundaries_are_discontinuous: true;
  continuity_evidence: ScannerFrameContinuityEvidenceV1[];
  configuration: Omit<ScannerReportV1["configuration"], "schema_version" | "kernel_buffers"> & {
    schema_version: 2;
    kernel_buffers: number;
    tuning_settle_us: number;
    require_device_metadata: true;
    reset_receive_buffer_before_each_target: true;
  };
};

export type ScannerReportV3 = Omit<ScannerReportV2, "schema_version" | "kind" | "continuity_observable"> & {
  schema_version: 3;
  kind: "starlink_scanner_report_v3";
  continuity_observable: boolean;
  close_failure: {
    schema_version: 1;
    stage: "radio_close";
    exception_type: string;
    message: string;
  } | null;
};

export type ScannerCaptureReport = ScannerReportV1 | ScannerReportV2 | ScannerReportV3;

export interface ScannerHistoryPageV1 {
  schema_version: 1;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{ schema_version: 1; scanned_at: string; report: ScannerReportV1 }>;
}

export interface ScannerHistoryPageV2 {
  schema_version: 2;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 2;
    scanned_at: string;
    report: ScannerReportV1 | ScannerReportV2;
  }>;
}

export interface ScannerHistoryPageV3 {
  schema_version: 3;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 3;
    scanned_at: string;
    report: ScannerCaptureReport;
  }>;
}

export interface ScannerAnalysisHistoryPageV2 {
  schema_version: 2;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 2;
    captured_at: string;
    published_at: string;
    scan_id: string;
    analysis_id: string;
    report: ScannerReportV1;
  }>;
}

export interface ScannerAnalysisHistoryPageV3 {
  schema_version: 3;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 3;
    captured_at: string;
    published_at: string;
    scan_id: string;
    analysis_id: string;
    report: ScannerReportV1 | ScannerReportV2;
  }>;
}

export interface PersistentHopHistoryPageV1 {
  schema_version: 1;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 1;
    captured_at: string;
    finalized_at: string;
    session_id: string;
    radio_id: string;
    nominal_duration_seconds: 300;
    valid_visit_ms: 120;
    sample_rate_hz: 2500000 | 5000000;
    bandwidth_hz: 2500000 | 5000000;
    visit_count: number;
    target_coverage: Array<{
      schema_version: 1;
      target_index: number;
      target: {
        channel: number;
        edge: "lower" | "upper";
        rf_center_hz: number;
        if_center_hz: number;
      };
      visit_count: number;
      valid_sample_count: number;
    }>;
    capture_outcome: "complete" | "cancelled" | "failed";
    terminal_state: "completed" | "cancelled" | "failed";
    terminal_reason: string;
    valid_duty_ppm: number;
    continuity_attested: boolean;
    restoration_status: "restored" | "failed";
    qualified: boolean;
    analysis_state: "pending_backpressure";
    analysis_reason: string;
  }>;
}

export type PersistentHopCaptureV1 = PersistentHopHistoryPageV1["items"][number];

export interface PersistentHopAnalysisStatusV1 {
  schema_version: 1;
  session_id: string;
  analysis_id: "persistent-hop-glrt64-cfo-v1";
  state: "pending" | "running" | "complete" | "failed";
  total_visits: number;
  analyzed_visits: number;
  updated_at: string;
  failure_summary: string | null;
}

export type PersistentHopArtifact = "coverage" | "glrt64-response" | "cfo-trajectories";

export interface PersistentHopHistoryPageV2 {
  schema_version: 2;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 2;
    capture: PersistentHopCaptureV1;
    analysis: PersistentHopAnalysisStatusV1;
    available_artifacts: PersistentHopArtifact[];
  }>;
}

export interface PersistentHopSessionDetailV1 {
  schema_version: 1;
  capture: PersistentHopCaptureV1;
  analysis: PersistentHopAnalysisStatusV1;
  product: null | {
    schema_version: 1;
    analysis_id: "persistent-hop-glrt64-cfo-v1";
    session_id: string;
    completed_at: string;
    sample_rate_hz: 2500000 | 5000000;
    bandwidth_hz: 2500000 | 5000000;
    configuration: {
      probe_ms: number;
      probe_stride_ms: number;
      glrt64_margin_gate: number;
      maximum_acquisition_candidates: number;
    };
    visit_count: number;
    sweep_count: number;
    probe_count: number;
    passed_best_count: number;
    artifacts: Array<{ name: PersistentHopArtifact; byte_count: number; sha256: string }>;
  };
}

export interface PersistentHopAnalysisStatusV2 {
  schema_version: 2;
  session_id: string;
  analysis_id: "persistent-hop-fractional-glrt64-cfo-v2";
  state: "pending" | "running" | "complete" | "failed";
  total_visits: number;
  analyzed_visits: number;
  updated_at: string;
  failure_summary: string | null;
}

export interface PersistentHopHistoryPageV3 {
  schema_version: 3;
  cursor: number;
  limit: number;
  total: number;
  next_cursor: number | null;
  items: Array<{
    schema_version: 3;
    capture: PersistentHopCaptureV1;
    analysis: PersistentHopAnalysisStatusV2;
    available_artifacts: PersistentHopArtifact[];
  }>;
}

export interface PersistentHopSessionDetailV2 {
  schema_version: 2;
  capture: PersistentHopCaptureV1;
  analysis: PersistentHopAnalysisStatusV2;
  product: null | {
    schema_version: 2;
    analysis_id: "persistent-hop-fractional-glrt64-cfo-v2";
    session_id: string;
    completed_at: string;
    sample_rate_hz: 2500000 | 5000000;
    bandwidth_hz: 2500000 | 5000000;
    configuration: {
      probe_ms: number;
      probe_stride_ms: number;
      glrt64_margin_gate: number;
      maximum_acquisition_candidates: number;
      timing_refinement: "circular-five-cell-log-parabola-plus-lanczos16-v1";
      decision_score: "fractional-epoch-conditioned-glrt64-v1";
      require_fractional_epoch_for_decision: true;
    };
    visit_count: number;
    sweep_count: number;
    probe_count: number;
    fractionally_scored_candidate_count: number;
    passed_fractional_candidate_count: number;
    fractionally_scored_best_count: number;
    passed_fractional_best_count: number;
    artifacts: Array<{ name: PersistentHopArtifact; byte_count: number; sha256: string }>;
  };
}

export interface PersistentHopTrackingDetailV1 {
  schema_version: 1;
  status: {
    schema_version: 1;
    session_id: string;
    analysis_id: "persistent-hop-causal-tle-tracking-v1";
    state: "pending" | "running" | "complete" | "unsupported" | "failed";
    phase: "waiting" | "projection" | "trajectory" | "tle-matching" | "complete";
    completed_groups: number;
    total_groups: number;
    updated_at: string;
    failure_summary: string | null;
  };
  product: null | {
    schema_version: 1;
    session_id: string;
    terminal_outcome: "complete" | "no-trajectory" | "unsupported";
    terminal_reasons: string[];
    observer_site: null | { label: string; latitude_deg: number; longitude_deg: number; altitude_m: number };
    tle_snapshot: null | { provider: string; collected_utc_ns: number; digest: string; object_count: number };
    input_probe_count: number;
    nonoverlapping_probe_count: number;
    passing_fractional_candidate_count: number;
    projected_candidate_count: number;
    trajectory_hypothesis_count: number;
    physical_group_count: number;
    tle_matching_group_limit: number;
    tle_matching_attempted_group_count: number;
    unscored_physical_group_count: number;
    tracklets: Array<{
      tracklet_id: string;
      channel: number;
      edge: "lower" | "upper";
      receiver_id: number;
      observation_count: number;
      normalized_rate_hz_per_s: number;
      residual_rms_hz: number;
    }>;
    tle_candidates: Array<{
      hypothesis_rank: number;
      physical_group_id: string;
      tracklet_ids: string[];
      source_observation_count: number;
      support_span_s: number;
      nominal_candidate_count: number;
      leading_catalog_number: number | null;
      selected_tau_s: number | null;
      training_leader_heldout_rank: number;
      leading_candidate_persisted_on_heldout: boolean;
      abstention_recommended: boolean;
      abstention_reasons: string[];
      candidate_only: true;
      identity_claimed: false;
    }>;
    artifact: null | { name: "trajectory-tle"; byte_count: number; sha256: string };
    candidate_only: true;
    identity_claimed: false;
  };
}

export function getScannerReports(
  cursor = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<ScannerHistoryPageV3> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<ScannerHistoryPageV3>(`/api/v3/scanner/reports?${params}`, signal);
}

export function getScannerAnalyses(
  cursor = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<ScannerAnalysisHistoryPageV3> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<ScannerAnalysisHistoryPageV3>(`/api/v3/scanner/analyses?${params}`, signal);
}

export function getPersistentHopSessions(
  cursor = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<PersistentHopHistoryPageV3> {
  const params = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  return getJson<PersistentHopHistoryPageV3>(`/api/v3/scanner/persistent-sessions?${params}`, signal);
}

export function getPersistentHopSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<PersistentHopSessionDetailV2> {
  return getJson<PersistentHopSessionDetailV2>(
    `/api/v3/scanner/persistent-sessions/${encodeURIComponent(sessionId)}`,
    signal,
  );
}

export function getPersistentHopTracking(
  sessionId: string,
  signal?: AbortSignal,
): Promise<PersistentHopTrackingDetailV1> {
  return getJson<PersistentHopTrackingDetailV1>(
    `/api/v4/scanner/persistent-sessions/${encodeURIComponent(sessionId)}/tracking`,
    signal,
  );
}

export function persistentHopTrackingPngUrl(sessionId: string): string {
  return `/api/v4/scanner/persistent-sessions/${encodeURIComponent(sessionId)}/trajectory-tle.png`;
}

export function persistentHopAnalysisPngUrl(
  sessionId: string,
  artifact: PersistentHopArtifact,
): string {
  return `/api/v3/scanner/persistent-sessions/${encodeURIComponent(sessionId)}/${artifact}.png`;
}

export function scannerAnalysisPngUrl(
  scanId: string,
  analysisId: string,
  artifact:
    | "waterfall"
    | "glrt64"
    | "pilot-doppler"
    | "pilot-carrier-tracking"
    | "pilot-segment-rates",
): string {
  return `/api/v1/scanner/analyses/${encodeURIComponent(scanId)}/${encodeURIComponent(analysisId)}/${artifact}.png`;
}

export function getStatus(signal?: AbortSignal): Promise<SystemStatusV1> {
  return getJson<SystemStatusV1>("/api/v1/status", signal);
}

export function getControlStatus(signal?: AbortSignal): Promise<AnalysisControlStatusV2> {
  return getJson<AnalysisControlStatusV2>("/api/v2/control/status", signal);
}

export function getActiveQueue(signal?: AbortSignal): Promise<ActiveQueueV1> {
  return getJson<ActiveQueueV1>("/api/v1/queue?limit=200", signal);
}

export function getAcquisitionQueue(signal?: AbortSignal): Promise<AcquisitionQueueV1> {
  return getJson<AcquisitionQueueV1>("/api/v1/acquisition-queue?limit=200", signal);
}

export function searchRecordings(
  query: string,
  includeTest: boolean,
  analysisState: string,
  signal?: AbortSignal,
): Promise<RecordingSearchResponseV1> {
  const params = new URLSearchParams({
    include_test: String(includeTest),
    limit: "100",
  });
  if (query.trim()) params.set("query", query.trim());
  if (analysisState) params.set("analysis_state", analysisState);
  return getJson<RecordingSearchResponseV1>(`/api/v1/recordings?${params}`, signal);
}

export function getRecording(sessionId: string, signal?: AbortSignal): Promise<RecordingDetailV1> {
  return getJson<RecordingDetailV1>(`/api/v1/recordings/${encodeURIComponent(sessionId)}`, signal);
}

export function getRecordingRadioSetup(
  sessionId: string,
  signal?: AbortSignal,
): Promise<RecordingRadioSetupV2> {
  return getJson<RecordingRadioSetupV2>(
    `/api/v2/recordings/${encodeURIComponent(sessionId)}/radio-setup`,
    signal,
  );
}

export function reprocessRecording(sessionId: string): Promise<StandardReprocessResultV1> {
  return postJson<StandardReprocessResultV1>(
    `/api/v2/control/recordings/${encodeURIComponent(sessionId)}/reprocess`,
  );
}

export function runResearchAnalysis(sessionId: string): Promise<ResearchReprocessResultV1> {
  return postJson<ResearchReprocessResultV1>(
    `/api/v2/control/recordings/${encodeURIComponent(sessionId)}/research`,
  );
}

export function getProductContent(
  productId: string,
  signal?: AbortSignal,
): Promise<ProductContentV1> {
  return getJson<ProductContentV1>(
    `/api/v1/products/${encodeURIComponent(productId)}/content?maximum_points=192`,
    signal,
  );
}
