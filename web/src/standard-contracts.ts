export type StandardSubjectKindV2 = "receiver_path" | "radio" | "paired";
export type StandardSubjectStateV2 =
  | "not_analyzed"
  | "queued"
  | "running"
  | "blocked"
  | "partial"
  | "complete"
  | "current"
  | "stale"
  | "failed"
  | "unavailable";
export type StandardViewKindV2 =
  | "quality"
  | "power"
  | "waterfall"
  | "glrt64"
  | "cfo_trajectory"
  | "qam";

export interface StandardPipelineReleaseV2 {
  authoritative_pipeline_release_id: string;
  source_revision: string;
  family: "standard-glrt64-v2";
  display_version: string;
  graph_digest: string;
  configuration_digest: string;
  environment_digest: string;
}

export interface StandardEligibilityV2 {
  source_type: "LIVE" | "IMPORT" | "TEST";
  capture_committed: boolean;
  capture_healthy: boolean;
  automatic_eligible: boolean;
  explicit_eligible: boolean;
  promotion_allowed: boolean;
  evidence_only: boolean;
  exclusion_tags: string[];
  reason: string;
}

export interface StandardStateReasonV2 {
  code: string | null;
  message: string;
  affected_stage_keys: string[];
  affected_subject_ids: string[];
}

export interface StandardReceiverPathRefV2 {
  path_id: string;
  radio_id: string;
  radio_label: string;
  receiver_id: number;
  receiver_label: string;
  scope: {
    schema_version: 1;
    kind: "receiver_path";
    session_id: string;
    stream_id: string;
    radio_id: null;
    receiver_id: number;
    synchronization_inventory_digest: null;
  };
  scope_digest: string;
}

export interface StandardSubjectSummaryV2 {
  subject_id: string;
  session_id: string;
  subject_kind: StandardSubjectKindV2;
  label: string;
  derived: boolean;
  receiver_paths: StandardReceiverPathRefV2[];
  expected_path_count: number;
  completed_path_count: number;
  child_subject_ids: string[];
  state: StandardSubjectStateV2;
  ordinary_current: boolean;
  state_reasons: StandardStateReasonV2[];
  pipeline_release: StandardPipelineReleaseV2 | null;
  desired_pipeline_release_id: string;
  reuse: {
    computed_stage_count: number;
    reused_stage_count: number;
    recompute_stage_count: number;
    blocked_stage_count: number;
    reused_from_run_ids: string[];
    reason: string;
  };
  eligibility: StandardEligibilityV2;
  evidence_label: "candidate evidence only";
}

export interface StandardSubjectHierarchyV2 {
  schema_version: 2;
  session_id: string;
  source_type: "LIVE" | "IMPORT" | "TEST";
  eligibility: StandardEligibilityV2;
  generated_at: string;
  rows: StandardSubjectSummaryV2[];
}

export interface StandardTimeDomainV2 {
  absolute_start_utc: string;
  absolute_end_utc: string;
  elapsed_start_s: number;
  elapsed_end_s: number;
  time_unit: "s";
  timing_uncertainty_s: number;
}

export interface StandardSubjectDetailV2 {
  schema_version: 2;
  subject: StandardSubjectSummaryV2;
  time_domain: StandardTimeDomainV2;
  receiver_path_expansions: StandardSubjectSummaryV2[];
  receiver_path_evidence: Array<{
    receiver_path: StandardReceiverPathRefV2;
    coverage_fraction: number;
    analyzed_seconds: number;
    declared_seconds: number;
    quality_state: "complete" | "partial" | "failed" | "unavailable";
    clipped_fraction: number | null;
    continuity_gap_count: number | null;
    calibration_state: "applicable" | "unavailable" | "not_required";
    calibration_id: string | null;
    calibration_digest: string | null;
    frequency_uncertainty_hz: number | null;
    reason: string;
  }>;
  stage_source_count: number;
  stages: Array<{
    stage_key: string;
    subject_id: string;
    disposition: "computed" | "reused" | "recompute" | "blocked" | "not_required";
    runtime_seconds: number | null;
    output_digest: string | null;
    reused_from_run_id: string | null;
    reason: string;
  }>;
  stages_truncated: boolean;
  trajectory_source_count: number;
  trajectories: Array<{
    trajectory_id: string;
    receiver_path_id: string;
    algorithm: string;
    degree: 1 | 2 | 3;
    reference_time_s: number;
    coefficients_hz: number[];
    support_count: number;
    residual_rms_hz: number;
    bic: number;
    selected_for_correction: boolean;
    corrected_glrt64_gain: number | null;
    status: "selected" | "retained" | "rejected";
    rejection_reason: string | null;
  }>;
  trajectories_truncated: boolean;
  views: Array<{
    view_kind: StandardViewKindV2;
    state: "available" | "partial" | "unavailable";
    href: string;
    source_point_count: number;
    reason: string;
  }>;
  limitations: string[];
}

export interface StandardSeriesPointV2 { time_s: number; value: number }

export interface StandardAxisBoundsV2 {
  axis_id: "time" | "frequency_hz" | "metric_value" | "power_db";
  label: string;
  unit: string;
  full_source_min: number;
  full_source_max: number;
}

export interface StandardPlotViewV2 {
  schema_version: 2;
  session_id: string;
  subject_id: string;
  view_kind: StandardViewKindV2;
  state: "available" | "partial" | "unavailable";
  time_domain: StandardTimeDomainV2;
  receiver_path_ids: string[];
  horizontal_axis: StandardAxisBoundsV2;
  vertical_axis: StandardAxisBoundsV2;
  color_axis: StandardAxisBoundsV2 | null;
  source_point_count: number;
  returned_point_count: number;
  truncated: boolean;
  series: Array<{
    series_id: string;
    receiver_path_id: string;
    label: string;
    unit: string;
    source_point_count: number;
    points: StandardSeriesPointV2[];
    truncated: boolean;
    source_min: number | null;
    source_max: number | null;
  }>;
  waterfall_cells: Array<{
    receiver_path_id: string;
    time_s: number;
    frequency_hz: number;
    power_db: number;
  }>;
  cfo_observations: Array<{
    observation_id: string;
    receiver_path_id: string;
    algorithm: string;
    time_s: number;
    baseband_cfo_hz: number;
    glrt64_response: number;
    used_by_trajectory_ids: string[];
  }>;
  trajectory_curves: Array<{
    trajectory_id: string;
    receiver_path_id: string;
    degree: 1 | 2 | 3;
    selected_for_correction: boolean;
    points: StandardSeriesPointV2[];
  }>;
  reason: string;
}
