export type StandardSubjectKindV2 = "receiver_path" | "radio" | "paired";
export type StandardExclusionTagV2 = "QUALIFICATION" | "CALIBRATION" | "ACCEPTANCE";
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
  exclusion_tags: StandardExclusionTagV2[];
  reason: string;
}

export interface StandardStateReasonV2 {
  code: string | null;
  message: string;
  affected_stage_keys: string[];
  affected_subject_ids: string[];
}

export interface StandardReceiverPathRefV2 {
  subject_id: string;
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
  alternate_track_source_count?: number;
  alternate_tracks?: Array<{
    receiver_path_id: string;
    track_id: string;
    start_s: number;
    end_s: number;
    span_s: number;
    support_count: number;
    weighted_support: number;
    slope_hz_per_s: number;
    acceleration_hz_per_s2: 0;
    intercept_mod_alias_hz: number;
    residual_rms_hz: number;
    residual_max_hz: number;
    maximum_gap_s: number;
    confidence: "strong_geometry" | "candidate_geometry";
    status: "research_only";
  }>;
  alternate_tracks_truncated?: boolean;
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
  source_extrema: {
    schema_version: 2;
    source_artifact_digest: string;
    source_content_digest: string;
    source_point_count: number;
    axes: Array<{
      axis_id: "frequency_hz" | "metric_value" | "power_db";
      source_min: number;
      source_max: number;
    }>;
    lanes: Array<{
      receiver_path_id: string;
      source_point_count: number;
      axes: Array<{
        axis_id: "frequency_hz" | "metric_value" | "power_db";
        source_min: number;
        source_max: number;
      }>;
    }>;
    canonical_digest: string;
  };
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

export type StandardNativeCoverageStatusV3 =
  | "complete"
  | "partial_coverage"
  | "insufficient_data";
export type StandardNativeScientificDispositionV3 =
  | "candidate"
  | "no_candidate"
  | "insufficient";
export type StandardNativeArtifactNameV3 = "waterfall" | "cfo-alternate";
export type StandardNativePngArtifactNameV4 =
  | "waterfall"
  | "pilot-methods"
  | "cfo-raw"
  | "cfo-dealiased"
  | "cfo-final"
  | "cfo-alternate"
  | "trajectory-accounting"
  | "full-capture-glrt20ms"
  | "pilot-doppler"
  | "pilot-carrier-tracking"
  | "pilot-segment-rates";
export type StandardNativePngArtifactNameV8 =
  | StandardNativePngArtifactNameV4
  | "doppler-waterfall";
export type StandardNativePngArtifactNameV10 =
  | StandardNativePngArtifactNameV8
  | "glrt-epoch-timing"
  | "glrt-epoch-rate";
export type StandardNativePngArtifactNameV11 =
  | "waterfall"
  | "doppler-waterfall"
  | "pilot-methods"
  | "cfo-raw"
  | "cfo-dealiased"
  | "cfo-final"
  | "pss-glrt-frame-comparison";
export type StandardNativePngArtifactNameV12 = StandardNativePngArtifactNameV10;
export type StandardNativePngArtifactNameV13 = StandardNativePngArtifactNameV11;

export interface StandardNativePngArtifactV4 {
  schema_version: 4;
  name: StandardNativePngArtifactNameV4;
  label: string;
  description: string;
  href: string;
  catalog_kind: string;
  product_schema_version: number;
  digest: string;
  byte_size: number;
  media_type: "image/png";
}

export interface StandardNativePngArtifactV8
  extends Omit<StandardNativePngArtifactV4, "schema_version" | "name"> {
  schema_version: 8;
  name: StandardNativePngArtifactNameV8;
}

export interface StandardNativePngArtifactV10
  extends Omit<StandardNativePngArtifactV8, "schema_version" | "name"> {
  schema_version: 10;
  name: StandardNativePngArtifactNameV10;
}

export interface StandardNativePngArtifactV11
  extends Omit<StandardNativePngArtifactV8, "schema_version" | "name"> {
  schema_version: 11;
  name: StandardNativePngArtifactNameV11;
}

export interface StandardNativePngArtifactV12
  extends Omit<StandardNativePngArtifactV10, "schema_version" | "name"> {
  schema_version: 12;
  name: StandardNativePngArtifactNameV12;
}

export interface StandardNativePngArtifactV13
  extends Omit<StandardNativePngArtifactV11, "schema_version" | "name"> {
  schema_version: 13;
  name: StandardNativePngArtifactNameV13;
}

export interface StandardNativePngArtifactInventoryV4 {
  schema_version: 4;
  session_id: string;
  subject_id: string;
  subject_kind: "receiver_path" | "radio" | "paired";
  run_id: string;
  run_manifest_digest: string;
  sample_rate_hz: 2_500_000 | 3_000_000 | 5_000_000 | 10_000_000;
  coverage_status: StandardNativeCoverageStatusV3;
  artifacts: StandardNativePngArtifactV4[];
  content_digest: string;
}

export interface StandardNativePngArtifactInventoryV5 {
  schema_version: 5;
  session_id: string;
  subject_id: string;
  subject_kind: "receiver_path" | "radio" | "paired";
  run_id: string;
  run_manifest_digest: string;
  sample_rates_hz: Array<2_500_000 | 5_000_000 | 10_000_000>;
  coverage_status: StandardNativeCoverageStatusV3;
  artifacts: StandardNativePngArtifactV4[];
  content_digest: string;
}

export interface StandardNativePngArtifactInventoryV6
  extends Omit<StandardNativePngArtifactInventoryV5, "schema_version" | "sample_rates_hz"> {
  schema_version: 6;
  sample_rates_hz: Array<2_500_000 | 5_000_000 | 10_000_000 | 15_000_000 | 20_000_000>;
}

export interface StandardNativePngArtifactInventoryV7
  extends Omit<StandardNativePngArtifactInventoryV5, "schema_version" | "sample_rates_hz"> {
  schema_version: 7;
  sample_rates_hz: Array<
    2_500_000 | 3_000_000 | 5_000_000 | 10_000_000 | 15_000_000 | 20_000_000
  >;
}

export interface StandardNativePngArtifactInventoryV8
  extends Omit<
    StandardNativePngArtifactInventoryV7,
    "schema_version" | "artifacts"
  > {
  schema_version: 8;
  artifacts: StandardNativePngArtifactV8[];
}

export interface StandardNativePngArtifactInventoryV9
  extends Omit<
    StandardNativePngArtifactInventoryV8,
    "schema_version" | "sample_rates_hz"
  > {
  schema_version: 9;
  sample_rates_hz: Array<
    2_500_000 | 3_000_000 | 5_000_000 | 10_000_000 | 15_000_000 | 20_000_000 | 25_000_000
  >;
}

export interface StandardNativePngArtifactInventoryV10
  extends Omit<
    StandardNativePngArtifactInventoryV9,
    "schema_version" | "subject_kind" | "artifacts"
  > {
  schema_version: 10;
  subject_kind: "receiver_path";
  artifacts: StandardNativePngArtifactV10[];
}

export interface StandardNativePngArtifactInventoryV11
  extends Omit<
    StandardNativePngArtifactInventoryV9,
    "schema_version" | "subject_kind" | "sample_rates_hz" | "artifacts"
  > {
  schema_version: 11;
  subject_kind: "radio";
  sample_rates_hz: [2_500_000, 25_000_000];
  artifacts: StandardNativePngArtifactV11[];
}

export interface StandardNativePngArtifactInventoryV12
  extends Omit<StandardNativePngArtifactInventoryV10, "schema_version" | "artifacts"> {
  schema_version: 12;
  artifacts: StandardNativePngArtifactV12[];
}

export interface StandardNativePngArtifactInventoryV13
  extends Omit<StandardNativePngArtifactInventoryV11, "schema_version" | "artifacts"> {
  schema_version: 13;
  artifacts: StandardNativePngArtifactV13[];
}

export interface StandardNativePipelineReleaseV3 {
  schema_version: 3;
  family: "standard-native-v1";
  authoritative_pipeline_release_id: string;
  source_revision: string;
  pipeline_definition_id: string;
  graph_digest: string;
  configuration_digest: string;
  environment_digest: string;
}

export interface StandardNativeEligibilityV3 {
  schema_version: 3;
  source_type: "LIVE";
  source_manifest_schema_version: 3;
  capture_state: "committed" | "degraded";
  capture_committed: boolean;
  capture_healthy: true;
  full_device_span: true;
  validity_aware: true;
  automatic_eligible: true;
  explicit_eligible: true;
  promotion_allowed: true;
  evidence_only: false;
  profile_revision_digest: string;
  sample_rate_hz: 2_500_000 | 3_000_000 | 5_000_000 | 10_000_000;
  pipeline_definition_id: string;
  promotion_authority_digest: string;
  reason:
    | "Promoted reviewed V3 Standard-native capture is Current"
    | "Promoted reviewed V3 Standard-native capture is Current with partial validity coverage";
}

export interface StandardNativeMixedLegV4 {
  schema_version: 4;
  stream_id: string;
  radio_id: string;
  profile_name: string;
  profile_revision_digest: string;
  starlink_channel: 1 | 2 | 3 | 4;
  starlink_edge: "lower" | "upper";
  sample_rate_hz: 2_500_000 | 5_000_000 | 10_000_000;
  rf_bandwidth_hz: 2_500_000 | 5_000_000 | 10_000_000;
  tuned_center_frequency_hz: number;
  pilot_if_center_frequency_hz: number;
  channel_if_start_hz: number;
  channel_if_stop_hz: number;
  captured_if_start_hz: number;
  captured_if_stop_hz: number;
}

export interface StandardNativeEligibilityV4 {
  schema_version: 4;
  source_type: "LIVE";
  source_manifest_schema_version: 4;
  capture_state: "committed" | "degraded";
  capture_committed: boolean;
  capture_healthy: true;
  full_device_span: true;
  validity_aware: true;
  automatic_eligible: true;
  explicit_eligible: true;
  promotion_allowed: true;
  evidence_only: false;
  dwell_class: "mixed_2p5_5" | "mixed_2p5_10";
  legs: [StandardNativeMixedLegV4, StandardNativeMixedLegV4];
  pipeline_definition_id: string;
  promotion_authority_digest: string;
  resampled: false;
  reason:
    | "Promoted reviewed mixed Standard-native capture is Current"
    | "Promoted reviewed mixed Standard-native capture is Current with partial validity coverage";
}

export type StandardNativeProductionSampleRateV5 =
  | 2_500_000
  | 5_000_000
  | 10_000_000
  | 15_000_000
  | 20_000_000;

export type StandardNativeProductionSampleRateV6 =
  | StandardNativeProductionSampleRateV5
  | 25_000_000;

export interface StandardNativeProductionLegV5 {
  schema_version: 5;
  stream_id: string;
  radio_id: string;
  profile_name: string;
  profile_revision_digest: string;
  receiver_ids: [0] | [1] | [0, 1];
  gain_controller_mode: "tandem_hold" | "tandem_auto";
  gain_controller_request_digest: string;
  starlink_channel: 1 | 2 | 3 | 4;
  starlink_edge: "lower" | "upper";
  sample_rate_hz: StandardNativeProductionSampleRateV5;
  rf_bandwidth_hz: StandardNativeProductionSampleRateV5;
  tuned_center_frequency_hz: number;
  pilot_if_center_frequency_hz: number;
  channel_if_start_hz: number;
  channel_if_stop_hz: number;
  captured_if_start_hz: number;
  captured_if_stop_hz: number;
  logical_sample_count: number;
  validity_inventory_digest: string;
  timeline_digest: string;
  metadata_abi_version: 3;
}

export interface StandardNativeEligibilityV5 {
  schema_version: 5;
  source_type: "LIVE";
  source_manifest_schema_version: 5;
  capture_state: "committed" | "degraded";
  capture_committed: boolean;
  capture_healthy: true;
  full_device_span: true;
  validity_aware: true;
  automatic_eligible: true;
  explicit_eligible: true;
  promotion_allowed: true;
  evidence_only: false;
  dwell_class:
    | "both_2p5"
    | "both_5"
    | "mixed_2p5_5"
    | "mixed_2p5_10"
    | "mixed_2p5_15"
    | "mixed_2p5_20";
  tuning_branch: "same" | "same_channel_opposite_edge" | "independent";
  legs: [StandardNativeProductionLegV5, StandardNativeProductionLegV5];
  scheduled_intent_digest: string;
  capture_plan_digest: string;
  capture_hardware_binding_digest: string;
  pipeline_definition_id: string;
  promotion_authority_digest: string;
  resampled: false;
  reason:
    | "Promoted reviewed production Standard-native capture is Current"
    | "Promoted reviewed production Standard-native capture is Current with partial validity coverage";
}

export interface StandardNativeProductionLegV6
  extends Omit<
    StandardNativeProductionLegV5,
    "schema_version" | "sample_rate_hz" | "rf_bandwidth_hz"
  > {
  schema_version: 6;
  sample_rate_hz: StandardNativeProductionSampleRateV6;
  rf_bandwidth_hz: StandardNativeProductionSampleRateV6;
}

export interface StandardNativeEligibilityV6
  extends Omit<
    StandardNativeEligibilityV5,
    "schema_version" | "source_manifest_schema_version" | "dwell_class" | "legs"
  > {
  schema_version: 6;
  source_manifest_schema_version: 6;
  dwell_class: StandardNativeEligibilityV5["dwell_class"] | "mixed_2p5_25";
  legs: [StandardNativeProductionLegV6, StandardNativeProductionLegV6];
}

export interface StandardNativeSufficientStatisticsV1 {
  schema_version: 1;
  receiver_path_count: number;
  valid_complex_sample_count: number;
  energy_sum_ci16_squared: number;
  clipped_component_count: number;
  clipped_complex_sample_count: number;
  clipped_complex_fraction: number;
  mean_power_full_scale_squared: number;
  full_scale_component_magnitude: 32768;
  constant_iq: boolean;
  minimum_i: number;
  maximum_i: number;
  minimum_q: number;
  maximum_q: number;
}

export interface StandardNativeProbeExecutionAccountingV1 {
  schema_version: 1;
  scheduled_count: number;
  valid_count: number;
  analyzed_count: number;
  candidate_count: number;
  no_candidate_count: number;
  insufficient_count: number;
  gap_excluded_count: number;
  continuity_boundary_excluded_count: number;
  outside_span_count: number;
  qam_complete_count: number;
  qam_no_result_count: number;
  qam_insufficient_count: number;
  qam_not_evaluated_count: number;
}

export interface StandardNativeQamSufficientStatisticsV1 {
  schema_version: 1;
  algorithm_version: "known-qin-primary-qam-sufficient-statistics-v1";
  qam_result_count: number;
  correct_symbol_count: number;
  symbol_count: number;
  frame_count: number;
  squared_error_sum: string;
  reference_energy_sum: string;
  hard_symbol_accuracy: string | null;
  rms_evm: string | null;
  known_symbols_only: true;
  invalid_device_axis_samples_included: false;
}

export interface StandardNativeTerminalTrackAccountingV1 {
  schema_version: 1;
  segment_count: number;
  analyzed_segment_count: number;
  source_trajectory_count: number;
  returned_trajectory_count: number;
  truncated_trajectory_count: number;
  cross_segment_association_permitted: false;
}

export interface StandardNativeValidUtcIntervalV1 {
  schema_version: 1;
  start_utc_ns: number;
  stop_utc_ns: number;
  timing_basis: "first-sample-bracket-nominal-rate-inner-v1";
}

export interface StandardNativeTerminalSummaryV3 {
  schema_version: 3;
  expected_complex_sample_count: number;
  valid_complex_sample_count: number;
  missing_complex_sample_count: number;
  coverage_fraction: number;
  coverage_status: StandardNativeCoverageStatusV3;
  sufficient_statistics: StandardNativeSufficientStatisticsV1;
  terminal_opportunities: StandardNativeProbeExecutionAccountingV1;
  qam_statistics: StandardNativeQamSufficientStatisticsV1;
  terminal_tracks: StandardNativeTerminalTrackAccountingV1;
  scientific_disposition: StandardNativeScientificDispositionV3;
  valid_utc_intervals: StandardNativeValidUtcIntervalV1[];
  valid_samples_only: true;
  stateful_resets_at_continuity_boundaries: true;
  cross_gap_operation_permitted: false;
  reducer_uses_sufficient_statistics: true;
}

export interface StandardNativeSubjectSummaryV3 {
  schema_version: 3;
  subject_id: string;
  session_id: string;
  subject_kind: StandardSubjectKindV2;
  label: string;
  derived: boolean;
  receiver_paths: StandardReceiverPathRefV2[];
  expected_path_count: number;
  completed_path_count: number;
  child_subject_ids: string[];
  state: "current";
  ordinary_current: true;
  coverage_status: StandardNativeCoverageStatusV3;
  scientific_disposition: StandardNativeScientificDispositionV3;
  pipeline_release: StandardNativePipelineReleaseV3;
  desired_pipeline_release_id: string;
  reuse: StandardSubjectSummaryV2["reuse"];
  eligibility: StandardNativeEligibilityV3;
  terminal: StandardNativeTerminalSummaryV3;
  evidence_label: "candidate evidence only";
}

export interface StandardNativeSubjectHierarchyV3 {
  schema_version: 3;
  session_id: string;
  source_type: "LIVE";
  eligibility: StandardNativeEligibilityV3;
  generated_at: string;
  rows: StandardNativeSubjectSummaryV3[];
}

export interface StandardNativeSubjectSummaryV4
  extends Omit<StandardNativeSubjectSummaryV3, "schema_version" | "eligibility"> {
  schema_version: 4;
  eligibility: StandardNativeEligibilityV4;
}

export interface StandardNativeSubjectHierarchyV4 {
  schema_version: 4;
  session_id: string;
  source_type: "LIVE";
  eligibility: StandardNativeEligibilityV4;
  generated_at: string;
  rows: StandardNativeSubjectSummaryV4[];
}

export interface StandardNativeSubjectSummaryV5
  extends Omit<StandardNativeSubjectSummaryV3, "schema_version" | "eligibility"> {
  schema_version: 5;
  eligibility: StandardNativeEligibilityV5;
}

export interface StandardNativeSubjectHierarchyV5 {
  schema_version: 5;
  session_id: string;
  source_type: "LIVE";
  eligibility: StandardNativeEligibilityV5;
  generated_at: string;
  rows: StandardNativeSubjectSummaryV5[];
}

export interface StandardNativeSubjectSummaryV6
  extends Omit<StandardNativeSubjectSummaryV5, "schema_version" | "eligibility"> {
  schema_version: 6;
  eligibility: StandardNativeEligibilityV6;
}

export interface StandardNativeSubjectHierarchyV6 {
  schema_version: 6;
  session_id: string;
  source_type: "LIVE";
  eligibility: StandardNativeEligibilityV6;
  generated_at: string;
  rows: StandardNativeSubjectSummaryV6[];
}

export interface StandardNativeAnalysisSelectionV1 {
  schema_version: 1;
  policy: "automatic_2p5_only";
  analyzed_stream_ids: [string];
  omitted_stream_ids: [string];
}

export interface StandardNativeSubjectSummaryV7
  extends Omit<StandardNativeSubjectSummaryV6, "schema_version"> {
  schema_version: 7;
  analysis_selection: StandardNativeAnalysisSelectionV1;
}

export interface StandardNativeSubjectHierarchyV7 {
  schema_version: 7;
  session_id: string;
  source_type: "LIVE";
  eligibility: StandardNativeEligibilityV6;
  analysis_selection: StandardNativeAnalysisSelectionV1;
  generated_at: string;
  rows: [StandardNativeSubjectSummaryV7];
}

export interface StandardNativePathEvidenceV3 {
  schema_version: 3;
  receiver_path: StandardReceiverPathRefV2;
  terminal: StandardNativeTerminalSummaryV3;
  declared_seconds: number;
  valid_seconds: number;
  continuity_segment_count: number;
  continuity_boundary_count: number;
  invalid_zero_fill_excluded: true;
}

export interface StandardNativeTrajectoryV3 {
  schema_version: 3;
  receiver_path_id: string;
  continuity_segment_index: number;
  trajectory_id: string;
  start_s: number;
  end_s: number;
  reference_time_s: number;
  polynomial_degree: 1 | 2 | 3;
  absolute_coefficients_hz: number[];
  support_count: number;
  automatic_correction_eligible: boolean;
  replay_tier: string;
  cross_segment_association_permitted: false;
}

export interface StandardNativeViewDescriptorV3 {
  schema_version: 3;
  view_kind: StandardViewKindV2;
  state: "available" | "partial" | "unavailable";
  href: string;
  source_point_count: number;
  png_available: boolean;
  png_href: string | null;
  reason: string;
}

export interface StandardNativeSubjectDetailV3 {
  schema_version: 3;
  subject: StandardNativeSubjectSummaryV3;
  time_domain: StandardTimeDomainV2;
  receiver_path_expansions: StandardNativeSubjectSummaryV3[];
  receiver_path_evidence: StandardNativePathEvidenceV3[];
  stage_source_count: number;
  stages: StandardSubjectDetailV2["stages"];
  stages_truncated: boolean;
  trajectory_source_count: number;
  trajectories: StandardNativeTrajectoryV3[];
  trajectories_truncated: boolean;
  views: StandardNativeViewDescriptorV3[];
  available_artifacts: StandardNativeArtifactNameV3[];
  limitations: string[];
}

export interface StandardNativeSubjectDetailV4
  extends Omit<
    StandardNativeSubjectDetailV3,
    "schema_version" | "subject" | "receiver_path_expansions"
  > {
  schema_version: 4;
  subject: StandardNativeSubjectSummaryV4;
  receiver_path_expansions: StandardNativeSubjectSummaryV4[];
}

export interface StandardNativeSubjectDetailV5
  extends Omit<
    StandardNativeSubjectDetailV3,
    "schema_version" | "subject" | "receiver_path_expansions"
  > {
  schema_version: 5;
  subject: StandardNativeSubjectSummaryV5;
  receiver_path_expansions: StandardNativeSubjectSummaryV5[];
}

export interface StandardNativeSubjectDetailV6
  extends Omit<
    StandardNativeSubjectDetailV5,
    "schema_version" | "subject" | "receiver_path_expansions"
  > {
  schema_version: 6;
  subject: StandardNativeSubjectSummaryV6;
  receiver_path_expansions: StandardNativeSubjectSummaryV6[];
}

export interface StandardNativeSubjectDetailV7
  extends Omit<
    StandardNativeSubjectDetailV6,
    "schema_version" | "subject" | "receiver_path_expansions"
  > {
  schema_version: 7;
  subject: StandardNativeSubjectSummaryV7;
  receiver_path_expansions: StandardNativeSubjectSummaryV7[];
}

export interface StandardNativePresentationProductRefV3 {
  schema_version: 3;
  product_id: number;
  scope_key: string;
  kind: string;
  product_schema_version: number;
  digest: string;
}

export interface StandardNativeSourceProofV3 {
  schema_version: 3;
  run_manifest_digest: string;
  products: StandardNativePresentationProductRefV3[];
  content_digest: string;
}

export interface StandardNativeMetricPointV3 {
  schema_version: 3;
  time_s: number;
  value: number | null;
  valid: boolean;
}

export interface StandardNativeMetricSeriesV3 {
  schema_version: 3;
  series_id: string;
  receiver_path_id: string;
  label: string;
  unit: "dBFS" | "fraction" | "response" | "accuracy" | "EVM";
  source_point_count: number;
  points: StandardNativeMetricPointV3[];
  truncated: boolean;
}

export interface StandardNativeWaterfallTileV3 {
  schema_version: 3;
  receiver_path_id: string;
  time_bin: number;
  time_start_s: number;
  time_stop_s: number;
  sample_start: number;
  sample_stop: number;
  transform_count: number;
  valid: boolean;
  power_dbfs: Array<number | null>;
}

export interface StandardNativePlotViewV3 {
  schema_version: 3;
  session_id: string;
  subject_id: string;
  view_kind: StandardViewKindV2;
  state: "available" | "partial" | "unavailable";
  time_domain: StandardTimeDomainV2;
  receiver_path_ids: string[];
  sample_rate_hz: 2_500_000 | 3_000_000 | 5_000_000 | 10_000_000;
  source_proof: StandardNativeSourceProofV3;
  source_point_count: number;
  returned_point_count: number;
  truncated: boolean;
  metric_series: StandardNativeMetricSeriesV3[];
  frequency_bin_centers_hz: number[];
  waterfall_tiles: StandardNativeWaterfallTileV3[];
  trajectories: StandardNativeTrajectoryV3[];
  reason: string;
  projection_digest: string;
}

export interface StandardNativeFrequencyAxisV4 {
  schema_version: 4;
  receiver_path_id: string;
  frequency_bin_centers_hz: number[];
}

export interface StandardNativePlotViewV4 {
  schema_version: 4;
  session_id: string;
  subject_id: string;
  view_kind: StandardViewKindV2;
  state: "available" | "partial" | "unavailable";
  time_domain: StandardTimeDomainV2;
  receiver_path_ids: string[];
  sample_rates_hz: Array<2_500_000 | 5_000_000 | 10_000_000>;
  source_proof: StandardNativeSourceProofV3;
  source_point_count: number;
  returned_point_count: number;
  truncated: boolean;
  metric_series: StandardNativeMetricSeriesV3[];
  frequency_axes: StandardNativeFrequencyAxisV4[];
  waterfall_tiles: StandardNativeWaterfallTileV3[];
  trajectories: StandardNativeTrajectoryV3[];
  reason: string;
  projection_digest: string;
}

export interface StandardNativePlotViewV5
  extends Omit<StandardNativePlotViewV4, "schema_version" | "sample_rates_hz"> {
  schema_version: 5;
  sample_rates_hz: StandardNativeProductionSampleRateV5[];
}

export interface StandardNativePlotViewV6
  extends Omit<StandardNativePlotViewV5, "schema_version" | "sample_rates_hz"> {
  schema_version: 6;
  sample_rates_hz: StandardNativeProductionSampleRateV6[];
}

export type StandardSubjectHierarchy =
  | StandardSubjectHierarchyV2
  | StandardNativeSubjectHierarchyV3
  | StandardNativeSubjectHierarchyV4
  | StandardNativeSubjectHierarchyV5
  | StandardNativeSubjectHierarchyV6
  | StandardNativeSubjectHierarchyV7;
export type StandardSubjectDetail =
  | StandardSubjectDetailV2
  | StandardNativeSubjectDetailV3
  | StandardNativeSubjectDetailV4
  | StandardNativeSubjectDetailV5
  | StandardNativeSubjectDetailV6
  | StandardNativeSubjectDetailV7;
export type StandardSubjectSummary =
  | StandardSubjectSummaryV2
  | StandardNativeSubjectSummaryV3
  | StandardNativeSubjectSummaryV4
  | StandardNativeSubjectSummaryV5
  | StandardNativeSubjectSummaryV6
  | StandardNativeSubjectSummaryV7;
export type StandardPlotView =
  | StandardPlotViewV2
  | StandardNativePlotViewV3
  | StandardNativePlotViewV4
  | StandardNativePlotViewV5
  | StandardNativePlotViewV6;

export interface StandardReplayAuditRowV1 {
  receiver_path_id: string;
  branch_id: string;
  alias_index: number;
  tier: "automatic" | "geometry_only" | "replay_rejected" | "insufficient";
  automatic_correction_eligible: boolean;
  geometry_display_eligible: boolean;
  evaluated_probe_count: number;
  evaluated_block_count: number;
  block_coverage_ratio: number;
  median_block_corrected_margin: number | null;
  harmful_block_count: number;
  maximum_consecutive_harmful_blocks: number;
  reasons: string[];
  retained_in_final: boolean;
}

export interface StandardReplayAuditV1 {
  schema_version: 1;
  session_id: string;
  subject_id: string;
  source_row_count: number;
  rows: StandardReplayAuditRowV1[];
  truncated: boolean;
}

export type StandardTrackGateVerdictV1 = "pass" | "fail" | "audit" | "not_applicable";

export interface StandardTrackGateAuditV1 {
  schema_version: 1;
  session_id: string;
  subject_id: string;
  stages: Array<{
    stage_key: string;
    label: string;
    description: string;
    source_track_count: number;
    rows: Array<{
      receiver_path_id: string;
      track_id: string;
      disposition: "passed" | "dropped" | "retained" | "display_only";
      reason: string;
      gates: Array<{
        gate_key: string;
        label: string;
        value: string;
        criterion: string;
        verdict: StandardTrackGateVerdictV1;
      }>;
    }>;
    truncated: boolean;
    limitation: string | null;
  }>;
}
