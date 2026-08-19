/* Shared presentation-v1 browser contract. Drift is guarded by tests/api. */

export const PRESENTATION_SCHEMA_VERSION = 1 as const;

export type SourceType = "LIVE" | "TEST" | "IMPORT";
export type CaptureHealth = "complete" | "partial" | "failed";
export type StorageState = "available" | "purged";
export type AnalysisState =
  | "no_result"
  | "queued"
  | "running"
  | "partial"
  | "failed"
  | "complete";
export type ProductStatus = "complete" | "partial" | "failed" | "no_result";
export type ComputeTier = "not_run" | "quick" | "standard" | "research";
export type ScientificConfidence =
  | "unassessed"
  | "candidate"
  | "qualified"
  | "rejected"
  | "insufficient";

export interface HoldV1 {
  held: boolean;
  reason: string | null;
}

export interface CoverageV1 {
  analyzed_fraction: number;
  analyzed_seconds: number;
  dwell_seconds: number;
  description: string;
}

export interface CurrentRunV1 {
  run_id: string;
  pipeline_release: string;
  state: AnalysisState;
  started_at: string;
  finished_at: string | null;
  is_current: true;
}

export interface AnalysisSummaryV1 {
  state: AnalysisState;
  current_run: CurrentRunV1 | null;
  coverage: CoverageV1 | null;
  failure_reason: string | null;
  no_result_reason: string | null;
  product_count: number;
}

export interface RecordingSummaryV1 {
  schema_version: 1;
  session_id: string;
  title: string;
  started_at: string;
  duration_seconds: number;
  source_type: SourceType;
  tags: string[];
  hold: HoldV1;
  capture_health: CaptureHealth;
  storage_state: StorageState;
  profile_name: string;
  radio_count: number;
  analysis: AnalysisSummaryV1;
}

export interface CaptureProfileV1 {
  profile_id: string;
  name: string;
  revision: number;
  sample_rate_hz: number;
  bandwidth_hz: number;
  dwell_seconds: number;
  center_frequency_hz: number;
  receiver_count_per_radio: number;
}

export interface RadioStreamV1 {
  radio_id: string;
  serial: string;
  receiver_labels: string[];
  state: CaptureHealth;
  captured_samples: number;
  sample_rate_hz: number;
  gain_db: number[];
  raw_path: string | null;
  continuity_gaps: number;
  clipped_samples: number;
}

export interface SynchronizationV1 {
  mode: "none" | "best_effort";
  grade: "not_requested" | "observed" | "degraded" | "unavailable";
  start_skew_ms: number | null;
  skew_uncertainty_ms: number | null;
  overlap_seconds: number | null;
  overlap_fraction: number | null;
  timing_basis: string;
  phase_coherent: false;
}

export interface RecordingPathsV1 {
  recording_root: string;
  manifest_path: string;
  analysis_root: string | null;
}

export interface SeriesPointV1 {
  time_s: number;
  value: number;
}

export interface SeriesV1 {
  series_id: string;
  label: string;
  unit: string;
  points: SeriesPointV1[];
  source_point_count: number;
  decimated: boolean;
}

export interface AnalysisProductV1 {
  schema_version: 1;
  product_id: string;
  session_id: string;
  analysis_run_id: string;
  kind:
    | "quality"
    | "power"
    | "waterfall"
    | "detection"
    | "qam"
    | "doppler"
    | "controls"
    | "overlays"
    | "provenance";
  status: ProductStatus;
  content_type: "application/json";
  artifact_path: string;
  byte_count: number;
  sha256: string;
  coverage: CoverageV1 | null;
  summary: Record<string, unknown>;
}

export interface RecordingDetailV1 {
  schema_version: 1;
  session_id: string;
  title: string;
  started_at: string;
  duration_seconds: number;
  source_type: SourceType;
  tags: string[];
  hold: HoldV1;
  capture_health: CaptureHealth;
  storage_state: StorageState;
  profile: CaptureProfileV1;
  radios: RadioStreamV1[];
  synchronization: SynchronizationV1;
  paths: RecordingPathsV1;
  analysis: AnalysisSummaryV1;
  quality: {
    state: ProductStatus;
    clipped_fraction: number | null;
    constant_iq_refills: number | null;
    continuity_gaps: number | null;
    note: string | null;
  };
  power: SeriesV1[];
  detection: {
    state: "candidate" | "none" | "not_run" | "failed";
    known_pilot_candidate: boolean;
    calibrated_detection: boolean;
    qin_score: number | null;
    control_score: number | null;
    reason: string;
  };
  whole_dwell: {
    analysis_run_id: string | null;
    compute_tier: ComputeTier;
    confidence: ScientificConfidence;
    confidence_reason: string;
    candidate_count: number;
    returned_candidate_count: number;
    candidate_lineage_truncated: boolean;
    candidate_coverage: {
      scheduled_windows: number;
      complete_windows: number;
      searched_receiver_windows: number;
      searched_samples: number;
      searched_time_fraction: number;
      residual_cfo_min_hz: number;
      residual_cfo_max_hz: number;
      survey_config_digest: string;
    } | null;
    candidates: Array<{
      candidate_id: string;
      receiver_key: string;
      time_s: number;
      absolute_epoch_sample: number;
      search_residual_cfo_hz: number;
      baseband_cfo_hz: number;
      receiver_tuned_center_hz: number;
      tuned_signal_frequency_hz: number;
      verify_score: number;
      control_score: number;
      margin: number;
      rank_within_search: number;
      track_id: string | null;
      calibration_digest: string;
      parent_survey_config_digest: string;
    }>;
    controls: {
      state: ProductStatus;
      thresholds_calibrated: boolean;
      specificity_claimed: boolean;
      passed_candidate_count: number;
      best_held_out_margin: number | null;
      best_surrogate_margin: number | null;
      rejection_reasons: string[];
      reason: string;
    };
  };
  qam: {
    state: ProductStatus;
    combined_accuracy: number | null;
    receiver_accuracy: number[];
    rms_evm: number | null;
    frame_count: number;
    receiver_metrics: Array<{
      receiver_key: string;
      candidate_epoch_sample: number;
      baseband_cfo_hz: number;
      residual_cfo_refinement_hz: number;
      receiver_tuned_center_hz: number;
      tuned_signal_frequency_hz: number;
      accuracy: number;
      rms_evm: number;
      frame_count: number;
      noise_variance: number;
    }>;
    known_symbols_only: true;
  };
  doppler: {
    state: ProductStatus;
    slope_hz_per_s: number | null;
    baseband_cfo_at_reference_hz: number | null;
    receiver_tuned_center_hz: number | null;
    tuned_signal_frequency_at_reference_hz: number | null;
    frequency_span_hz: number | null;
    correlation: number | null;
    residual_rms_hz: number | null;
    point_count: number;
    motion_class: "dynamic" | "stationary_confounder" | "indeterminate" | null;
    confidence: ScientificConfidence;
    tle_candidate: string | null;
    association_status: "not_run" | "candidate" | "no_match" | "unavailable" | "failed";
  };
  /**
   * Authoritative per-stream scientific views. The top-level detection,
   * whole_dwell, qam, and doppler fields remain the primary-stream
   * compatibility projection.
   */
  stream_analyses: Array<{
    scope_key: string;
    radio_id: string;
    receiver_labels: string[];
    is_primary: boolean;
    detection: RecordingDetailV1["detection"];
    whole_dwell: RecordingDetailV1["whole_dwell"];
    qam: RecordingDetailV1["qam"];
    doppler: RecordingDetailV1["doppler"];
  }>;
  provenance: {
    analysis_run_id: string | null;
    pipeline_release: string | null;
    generated_at: string | null;
    config_digest: string | null;
    recording_digest: string;
    limitation_codes: string[];
  };
  products: AnalysisProductV1[];
}

export interface RecordingSearchResponseV1 {
  schema_version: 1;
  items: RecordingSummaryV1[];
  total: number;
  next_cursor: number | null;
}

export interface SystemStatusV1 {
  schema_version: 1;
  generated_at: string;
  storage: {
    total_bytes: number;
    used_bytes: number;
    used_fraction: number;
    retention_high_watermark: number;
    retention_low_watermark: number;
    admission_state: "open" | "warning" | "stopped";
  };
  backlog: {
    queued: number;
    running: number;
    failed: number;
    oldest_queued_seconds: number | null;
  };
  api_mode: "read_only";
}

export interface PlotPointV1 {
  x: number;
  y: number;
  value: number;
}

export interface ProductContentV1 {
  schema_version: 1;
  product_id: string;
  analysis_run_id: string;
  kind: string;
  source_point_count: number;
  returned_point_count: number;
  truncated: boolean;
  points: PlotPointV1[];
  metadata: Record<string, unknown>;
}
