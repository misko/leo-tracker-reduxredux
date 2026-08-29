import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { StandardAnalysis } from "./StandardAnalysis";
import {
  parseStandardNativePngArtifactInventory,
  parseStandardPlotView,
  parseStandardSubjectDetail,
  parseStandardSubjectHierarchy,
} from "./standard-contract-validation";
import type {
  StandardNativeEligibilityV3,
  StandardNativeEligibilityV4,
  StandardNativeEligibilityV5,
  StandardNativePngArtifactInventoryV4,
  StandardNativePngArtifactInventoryV5,
  StandardNativePngArtifactInventoryV6,
  StandardNativePngArtifactInventoryV7,
  StandardNativePlotViewV5,
  StandardNativePlotViewV3,
  StandardNativeSubjectDetailV3,
  StandardNativeSubjectDetailV4,
  StandardNativeSubjectDetailV5,
  StandardNativeSubjectHierarchyV3,
  StandardNativeSubjectHierarchyV4,
  StandardNativeSubjectHierarchyV5,
  StandardNativeSubjectSummaryV3,
  StandardNativeSubjectSummaryV4,
  StandardNativeSubjectSummaryV5,
  StandardNativeTerminalSummaryV3,
  StandardPlotViewV2,
  StandardSubjectDetailV2,
  StandardSubjectHierarchyV2,
  StandardSubjectSummaryV2,
  StandardViewKindV2,
} from "./standard-contracts";

const sha = "0123456789abcdef0123456789abcdef01234567";
const release = {
  authoritative_pipeline_release_id: sha,
  source_revision: sha,
  family: "standard-glrt64-v2" as const,
  display_version: "2.0.0",
  graph_digest: "a".repeat(64),
  configuration_digest: "b".repeat(64),
  environment_digest: "c".repeat(64),
};
const eligibility = {
  source_type: "TEST" as const,
  capture_committed: true,
  capture_healthy: true,
  automatic_eligible: false,
  explicit_eligible: true,
  promotion_allowed: false,
  evidence_only: true,
  exclusion_tags: [],
  reason: "Reviewed TEST corpus is explicit, non-current evidence only",
};
const paths = [0, 1].flatMap((radio) => [0, 1].map((receiver) => ({
  subject_id: `path:radio${radio}:rx${receiver}`,
  path_id: `radio${radio}:rx${receiver}`,
  radio_id: `radio${radio}`,
  radio_label: `Radio${radio}`,
  receiver_id: receiver,
  receiver_label: `RX${receiver}`,
  scope: {
    schema_version: 1 as const,
    kind: "receiver_path" as const,
    session_id: "T1",
    stream_id: `stream-${radio}`,
    radio_id: null,
    receiver_id: receiver,
    synchronization_inventory_digest: null,
  },
  scope_digest: "d".repeat(64),
})));

function subject(
  id: string,
  label: string,
  kind: "paired" | "radio" | "receiver_path",
  selectedPaths = paths,
  state: StandardSubjectSummaryV2["state"] = "complete",
): StandardSubjectSummaryV2 {
  return {
    subject_id: id,
    session_id: "T1",
    subject_kind: kind,
    label,
    derived: kind !== "receiver_path",
    receiver_paths: selectedPaths,
    expected_path_count: selectedPaths.length,
    completed_path_count: selectedPaths.length,
    child_subject_ids: kind === "paired" ? ["radio:radio0", "radio:radio1"] : kind === "radio" ? selectedPaths.map((item) => `path:${item.path_id}`) : [],
    state,
    ordinary_current: false,
    state_reasons: [],
    pipeline_release: release,
    desired_pipeline_release_id: sha,
    reuse: {
      computed_stage_count: 1,
      reused_stage_count: 8,
      recompute_stage_count: 0,
      blocked_stage_count: 0,
      reused_from_run_ids: ["run-source"],
      reason: "exact cache hit",
    },
    eligibility,
    evidence_label: "candidate evidence only",
  };
}

const pair = subject("pair:radio0:radio1", "Paired Radio0 + Radio1", "paired");
const hierarchy: StandardSubjectHierarchyV2 = {
  schema_version: 2,
  session_id: "T1",
  source_type: "TEST",
  eligibility,
  generated_at: "2026-08-19T18:00:00Z",
  rows: [
    pair,
    subject("radio:radio0", "Radio0", "radio", paths.slice(0, 2), "partial"),
    subject("radio:radio1", "Radio1", "radio", paths.slice(2), "failed"),
  ],
};
const domain = {
  absolute_start_utc: "2026-08-19T17:00:00Z",
  absolute_end_utc: "2026-08-19T17:01:00Z",
  elapsed_start_s: 0,
  elapsed_end_s: 60,
  time_unit: "s" as const,
  timing_uncertainty_s: 0.002,
};
const viewKinds: StandardViewKindV2[] = ["quality", "power", "waterfall", "glrt64", "cfo_trajectory", "qam"];
const detail: StandardSubjectDetailV2 = {
  schema_version: 2,
  subject: pair,
  time_domain: domain,
  receiver_path_expansions: paths.map((path) => subject(`path:${path.path_id}`, `${path.radio_label} ${path.receiver_label}`, "receiver_path", [path])),
  receiver_path_evidence: paths.map((path) => ({
    receiver_path: path,
    coverage_fraction: 1,
    analyzed_seconds: 60,
    declared_seconds: 60,
    quality_state: "complete",
    clipped_fraction: .00001,
    continuity_gap_count: 0,
    calibration_state: "applicable",
    calibration_id: `calibration:${path.path_id}`,
    calibration_digest: "c".repeat(64),
    frequency_uncertainty_hz: 125,
    reason: "full coverage",
  })),
  stage_source_count: 2,
  stages: [
    { stage_key: "path-pilot-scan", subject_id: pair.subject_id, disposition: "reused", runtime_seconds: 0.1, output_digest: "a".repeat(64), reused_from_run_id: "run-source", reason: "exact hit" },
    { stage_key: "paired-report", subject_id: pair.subject_id, disposition: "computed", runtime_seconds: 0.2, output_digest: "b".repeat(64), reused_from_run_id: null, reason: "children ready" },
  ],
  stages_truncated: false,
  trajectory_source_count: 1,
  trajectories: [{
    trajectory_id: "track-1", receiver_path_id: "radio0:rx0", algorithm: "glrt64", degree: 2,
    reference_time_s: 1, coefficients_hz: [2, -120, 253443.36], support_count: 27,
    residual_rms_hz: 312.5, bic: 84.1, selected_for_correction: true,
    corrected_glrt64_gain: 0.142, status: "selected", rejection_reason: null,
  }],
  trajectories_truncated: false,
  views: viewKinds.map((view_kind) => ({ view_kind, state: "available", href: `/view/${view_kind}`, source_point_count: 3, reason: "available" })),
  limitations: ["Candidate evidence only; source identity is unassessed; no payload recovery is claimed"],
};

const nativeRelease = {
  schema_version: 3 as const,
  family: "standard-native-v1" as const,
  authoritative_pipeline_release_id: sha,
  source_revision: sha,
  pipeline_definition_id: `sha256:${"1".repeat(64)}`,
  graph_digest: `sha256:${"2".repeat(64)}`,
  configuration_digest: `sha256:${"3".repeat(64)}`,
  environment_digest: `sha256:${"4".repeat(64)}`,
};
const nativeEligibility: StandardNativeEligibilityV3 = {
  schema_version: 3,
  source_type: "LIVE",
  source_manifest_schema_version: 3,
  capture_state: "degraded",
  capture_committed: false,
  capture_healthy: true,
  full_device_span: true,
  validity_aware: true,
  automatic_eligible: true,
  explicit_eligible: true,
  promotion_allowed: true,
  evidence_only: false,
  profile_revision_digest: `sha256:${"5".repeat(64)}`,
  sample_rate_hz: 3_000_000,
  pipeline_definition_id: nativeRelease.pipeline_definition_id,
  promotion_authority_digest: `sha256:${"6".repeat(64)}`,
  reason: "Promoted reviewed V3 Standard-native capture is Current with partial validity coverage",
};

function nativeTerminal(
  expected: number,
  valid: number,
  receiverPathCount: number,
  scheduled: number,
): StandardNativeTerminalSummaryV3 {
  const missing = expected - valid;
  const validOpportunities = Math.floor(scheduled / 2);
  const gapExcluded = scheduled > validOpportunities ? 1 : 0;
  const boundaryExcluded = scheduled - validOpportunities - gapExcluded;
  return {
    schema_version: 3,
    expected_complex_sample_count: expected,
    valid_complex_sample_count: valid,
    missing_complex_sample_count: missing,
    coverage_fraction: valid / expected,
    coverage_status: missing === 0 ? "complete" : "partial_coverage",
    sufficient_statistics: {
      schema_version: 1,
      receiver_path_count: receiverPathCount,
      valid_complex_sample_count: valid,
      energy_sum_ci16_squared: valid * 10,
      clipped_component_count: 0,
      clipped_complex_sample_count: 0,
      clipped_complex_fraction: 0,
      mean_power_full_scale_squared: (valid * 10) / (valid * 32768 ** 2),
      full_scale_component_magnitude: 32768,
      constant_iq: false,
      minimum_i: -2,
      maximum_i: 2,
      minimum_q: -3,
      maximum_q: 3,
    },
    terminal_opportunities: {
      schema_version: 1,
      scheduled_count: scheduled,
      valid_count: validOpportunities,
      analyzed_count: validOpportunities,
      candidate_count: 0,
      no_candidate_count: 0,
      insufficient_count: validOpportunities,
      gap_excluded_count: gapExcluded,
      continuity_boundary_excluded_count: boundaryExcluded,
      outside_span_count: 0,
      qam_complete_count: 0,
      qam_no_result_count: 0,
      qam_insufficient_count: validOpportunities,
      qam_not_evaluated_count: 0,
    },
    qam_statistics: {
      schema_version: 1,
      algorithm_version: "known-qin-primary-qam-sufficient-statistics-v1",
      qam_result_count: 0,
      correct_symbol_count: 0,
      symbol_count: 0,
      frame_count: 0,
      squared_error_sum: "0",
      reference_energy_sum: "0",
      hard_symbol_accuracy: null,
      rms_evm: null,
      known_symbols_only: true,
      invalid_device_axis_samples_included: false,
    },
    terminal_tracks: {
      schema_version: 1,
      segment_count: receiverPathCount * 2,
      analyzed_segment_count: receiverPathCount * 2,
      source_trajectory_count: 0,
      returned_trajectory_count: 0,
      truncated_trajectory_count: 0,
      cross_segment_association_permitted: false,
    },
    scientific_disposition: "insufficient",
    valid_utc_intervals: [{
      schema_version: 1,
      start_utc_ns: 1_000_000,
      stop_utc_ns: 2_000_000,
      timing_basis: "first-sample-bracket-nominal-rate-inner-v1",
    }],
    valid_samples_only: true,
    stateful_resets_at_continuity_boundaries: true,
    cross_gap_operation_permitted: false,
    reducer_uses_sufficient_statistics: true,
  };
}

function nativeSubject(
  id: string,
  label: string,
  kind: "radio" | "receiver_path",
  selectedPaths: typeof paths,
  terminal: StandardNativeTerminalSummaryV3,
): StandardNativeSubjectSummaryV3 {
  return {
    schema_version: 3,
    subject_id: id,
    session_id: "T1",
    subject_kind: kind,
    label,
    derived: kind === "radio",
    receiver_paths: selectedPaths,
    expected_path_count: selectedPaths.length,
    completed_path_count: selectedPaths.length,
    child_subject_ids: kind === "radio" ? selectedPaths.map((path) => path.subject_id) : [],
    state: "current",
    ordinary_current: true,
    coverage_status: terminal.coverage_status,
    scientific_disposition: terminal.scientific_disposition,
    pipeline_release: nativeRelease,
    desired_pipeline_release_id: sha,
    reuse: {
      computed_stage_count: 12,
      reused_stage_count: 0,
      recompute_stage_count: 0,
      blocked_stage_count: 0,
      reused_from_run_ids: [],
      reason: "Rendered for this run",
    },
    eligibility: nativeEligibility,
    terminal,
    evidence_label: "candidate evidence only",
  };
}

const nativePaths = paths.slice(0, 2);
const nativePathSubjects = nativePaths.map((path, index) => nativeSubject(
  path.subject_id,
  `${path.radio_label} ${path.receiver_label}`,
  "receiver_path",
  [path],
  nativeTerminal(50, 45, 1, 2),
));
const nativeRadio = nativeSubject(
  "radio:radio0",
  "Radio0",
  "radio",
  nativePaths,
  nativeTerminal(100, 90, 2, 4),
);
const nativeHierarchy: StandardNativeSubjectHierarchyV3 = {
  schema_version: 3,
  session_id: "T1",
  source_type: "LIVE",
  eligibility: nativeEligibility,
  generated_at: "2026-08-26T06:00:00Z",
  rows: [nativeRadio],
};
const nativeViews = viewKinds.map((view_kind) => ({
  schema_version: 3 as const,
  view_kind,
  state: view_kind === "waterfall" ? "partial" as const : "unavailable" as const,
  href: `/api/v2/recordings/T1/standard-subjects/radio:radio0/views/${view_kind}`,
  source_point_count: view_kind === "waterfall" ? 2 : 0,
  png_available: view_kind === "waterfall",
  png_href: view_kind === "waterfall"
    ? "/api/v2/recordings/T1/standard-subjects/radio:radio0/views/waterfall.png"
    : null,
  reason: view_kind === "waterfall" ? "Validity-aware native evidence is available with partial coverage" : "No sealed terminal evidence is available for this native view",
}));
const nativeEvidence = nativePathSubjects.map((path) => ({
  schema_version: 3 as const,
  receiver_path: path.receiver_paths[0],
  terminal: path.terminal,
  declared_seconds: 60,
  valid_seconds: 54,
  continuity_segment_count: 2,
  continuity_boundary_count: 1,
  invalid_zero_fill_excluded: true as const,
}));
const nativeDetail: StandardNativeSubjectDetailV3 = {
  schema_version: 3,
  subject: nativeRadio,
  time_domain: domain,
  receiver_path_expansions: nativePathSubjects,
  receiver_path_evidence: nativeEvidence,
  stage_source_count: 0,
  stages: [],
  stages_truncated: false,
  trajectory_source_count: 0,
  trajectories: [],
  trajectories_truncated: false,
  views: nativeViews,
  available_artifacts: ["waterfall"],
  limitations: [
    "Candidate evidence only; source identity is unassessed; no payload recovery is claimed",
    "Stateful algorithms reset at every continuity boundary",
    "Power, quality, QAM, and opportunity reducers use valid samples and sufficient statistics",
    "Waterfall tiles retain the global device-time axis and mark missing cells invalid",
    "Paired-radio support is the intersection of valid UTC intervals",
  ],
};
const nativePathDetail: StandardNativeSubjectDetailV3 = {
  ...nativeDetail,
  subject: nativePathSubjects[0],
  receiver_path_expansions: [nativePathSubjects[0]],
  receiver_path_evidence: [nativeEvidence[0]],
  views: nativeViews.map((view) => ({
    ...view,
    href: view.href.replace("radio:radio0", nativePathSubjects[0].subject_id),
    png_href: view.png_href?.replace("radio:radio0", nativePathSubjects[0].subject_id) ?? null,
  })),
  available_artifacts: ["waterfall", "cfo-alternate"],
};
const nativeArtifactRows = [
  ["waterfall", "Waterfall — frequency × time", "Fixed global device-time axis; missing support is blank", "standard.waterfall-png", 2, "views/waterfall.png"],
  ["pilot-methods", "Pilot detector comparison — GLRT64, Symbolwise, Anchor-8", "Wholly-valid probes with hard continuity resets", "standard.pilot-methods-png", 2, "views/glrt64.png"],
  ["cfo-raw", "CFO trajectories — Hough-seeded robust linear segments", "Reset-local raw trajectory geometry on the global time axis", "standard.cfo-trajectories-png", 2, "views/cfo_trajectory.png"],
  ["cfo-dealiased", "De-aliased CFO trajectories", "Canonical modulo-alias branches before absolute-lift replay", "standard.cfo-trajectories-dealiased-png", 2, "artifacts/cfo-dealiased.png"],
  ["cfo-final", "Final replay-classified CFO candidates", "Correction-eligible and display-only reset-local tracks", "standard.cfo-trajectories-final-png", 2, "artifacts/cfo-final.png"],
  ["cfo-alternate", "Alternate Hough CFO candidates", "Independent reset-local alternate Hough geometry", "standard.alternate-cfo-tracks-png", 3, "artifacts/cfo-alternate.png"],
  ["trajectory-accounting", "Trajectory-conditioned replay accounting", "Per-segment transition and support accounting", "standard.trajectory-conditioned-accounting-png", 3, "artifacts/trajectory-accounting.png"],
  ["full-capture-glrt20ms", "Independent 20 ms GLRT and local Doppler rate", "Globally scheduled valid windows with segment-local fits", "standard.full-capture-glrt20ms-png", 2, "artifacts/full-capture-glrt20ms.png"],
  ["pilot-doppler", "Pilot Doppler qualification overview", "Segment-local qualification and reacquisition evidence", "standard.pilot-doppler-segments-png", 3, "artifacts/pilot-doppler.png"],
  ["pilot-carrier-tracking", "Frame CFO and carrier-rate tracking", "Frame-level state with visible continuity resets", "standard.pilot-carrier-tracking-png", 3, "artifacts/pilot-carrier-tracking.png"],
  ["pilot-segment-rates", "Doppler rates across 50–75 ms segment regions", "Direct local rates remain separate across continuity segments", "standard.pilot-segment-rates-png", 3, "artifacts/pilot-segment-rates.png"],
] as const;

function nativeArtifactInventory(
  detail: StandardNativeSubjectDetailV3,
): StandardNativePngArtifactInventoryV4 {
  const path = `/api/v2/recordings/${encodeURIComponent(detail.subject.session_id)}/standard-subjects/${encodeURIComponent(detail.subject.subject_id)}`;
  const rows = detail.subject.subject_kind === "receiver_path"
    ? nativeArtifactRows
    : nativeArtifactRows.slice(0, 5);
  return {
    schema_version: 4,
    session_id: detail.subject.session_id,
    subject_id: detail.subject.subject_id,
    subject_kind: detail.subject.subject_kind,
    run_id: "run-native-current",
    run_manifest_digest: `sha256:${"d".repeat(64)}`,
    sample_rate_hz: detail.subject.eligibility.sample_rate_hz,
    coverage_status: detail.subject.coverage_status,
    artifacts: rows.map(([name, label, description, catalog_kind, product_schema_version, suffix], index) => ({
      schema_version: 4,
      name,
      label,
      description,
      href: `${path}/${suffix}`,
      catalog_kind,
      product_schema_version,
      digest: `sha256:${String((index % 9) + 1).repeat(64)}`,
      byte_size: 1000 + index,
      media_type: "image/png",
    })),
    content_digest: `sha256:${"e".repeat(64)}`,
  };
}

const mixedEligibility: StandardNativeEligibilityV4 = {
  schema_version: 4,
  source_type: "LIVE",
  source_manifest_schema_version: 4,
  capture_state: "degraded",
  capture_committed: false,
  capture_healthy: true,
  full_device_span: true,
  validity_aware: true,
  automatic_eligible: true,
  explicit_eligible: true,
  promotion_allowed: true,
  evidence_only: false,
  dwell_class: "mixed_2p5_5",
  legs: [{
    schema_version: 4,
    stream_id: "stream-0",
    radio_id: "radio0",
    profile_name: "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
    profile_revision_digest: `sha256:${"1".repeat(64)}`,
    starlink_channel: 3,
    starlink_edge: "lower",
    sample_rate_hz: 2_500_000,
    rf_bandwidth_hz: 2_500_000,
    tuned_center_frequency_hz: 1_459_687_500,
    pilot_if_center_frequency_hz: 1_459_687_500,
    channel_if_start_hz: 1_455_000_000,
    channel_if_stop_hz: 1_695_000_000,
    captured_if_start_hz: 1_458_437_500,
    captured_if_stop_hz: 1_460_937_500,
  }, {
    schema_version: 4,
    stream_id: "stream-1",
    radio_id: "radio1",
    profile_name: "starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
    profile_revision_digest: `sha256:${"2".repeat(64)}`,
    starlink_channel: 3,
    starlink_edge: "lower",
    sample_rate_hz: 5_000_000,
    rf_bandwidth_hz: 5_000_000,
    tuned_center_frequency_hz: 1_459_687_500,
    pilot_if_center_frequency_hz: 1_459_687_500,
    channel_if_start_hz: 1_455_000_000,
    channel_if_stop_hz: 1_695_000_000,
    captured_if_start_hz: 1_457_187_500,
    captured_if_stop_hz: 1_462_187_500,
  }],
  pipeline_definition_id: nativeRelease.pipeline_definition_id,
  promotion_authority_digest: `sha256:${"6".repeat(64)}`,
  resampled: false,
  reason: (
    "Promoted reviewed mixed Standard-native capture is Current with partial validity coverage"
  ),
};

function mixedSubject(
  base: StandardNativeSubjectSummaryV3,
): StandardNativeSubjectSummaryV4 {
  return {
    ...base,
    schema_version: 4,
    eligibility: mixedEligibility,
  };
}

const mixedPathSubjects = paths.map((path, index) => mixedSubject(nativeSubject(
  path.subject_id,
  `${path.radio_label} ${path.receiver_label}`,
  "receiver_path",
  [path],
  nativeTerminal(index < 2 ? 150 : 300, index < 2 ? 145 : 285, 1, 4),
)));
const mixedRadio0 = mixedSubject(nativeSubject(
  "radio:radio0",
  "Radio0",
  "radio",
  paths.slice(0, 2),
  nativeTerminal(300, 290, 2, 8),
));
const mixedRadio1 = mixedSubject(nativeSubject(
  "radio:radio1",
  "Radio1",
  "radio",
  paths.slice(2),
  nativeTerminal(600, 570, 2, 8),
));
const mixedPair: StandardNativeSubjectSummaryV4 = {
  ...mixedSubject(nativeSubject(
    "pair:radio0:radio1",
    "Paired Radio0 + Radio1",
    "radio",
    paths,
    nativeTerminal(900, 850, 4, 16),
  )),
  subject_kind: "paired",
  child_subject_ids: [mixedRadio0.subject_id, mixedRadio1.subject_id],
};
const mixedEvidence = mixedPathSubjects.map((path) => ({
  schema_version: 3 as const,
  receiver_path: path.receiver_paths[0],
  terminal: path.terminal,
  declared_seconds: 60,
  valid_seconds: 60 * path.terminal.coverage_fraction,
  continuity_segment_count: 2,
  continuity_boundary_count: 1,
  invalid_zero_fill_excluded: true as const,
}));
const mixedHierarchy: StandardNativeSubjectHierarchyV4 = {
  schema_version: 4,
  session_id: "T1",
  source_type: "LIVE",
  eligibility: mixedEligibility,
  generated_at: "2026-08-27T06:00:00Z",
  rows: [mixedPair, mixedRadio0, mixedRadio1],
};
const mixedDetail: StandardNativeSubjectDetailV4 = {
  ...nativeDetail,
  schema_version: 4,
  subject: mixedPair,
  receiver_path_expansions: mixedPathSubjects,
  receiver_path_evidence: mixedEvidence,
};

function mixedArtifactInventory(): StandardNativePngArtifactInventoryV5 {
  const path = `/api/v2/recordings/T1/standard-subjects/${encodeURIComponent(mixedPair.subject_id)}`;
  return {
    schema_version: 5,
    session_id: "T1",
    subject_id: mixedPair.subject_id,
    subject_kind: "paired",
    run_id: "run-mixed-current",
    run_manifest_digest: `sha256:${"d".repeat(64)}`,
    sample_rates_hz: [2_500_000, 5_000_000],
    coverage_status: mixedPair.coverage_status,
    artifacts: nativeArtifactRows.slice(0, 5).map(([
      name, label, description, catalog_kind, product_schema_version, suffix,
    ], index) => ({
      schema_version: 4,
      name,
      label,
      description,
      href: `${path}/${suffix}`,
      catalog_kind,
      product_schema_version,
      digest: `sha256:${String(index + 1).repeat(64)}`,
      byte_size: 2000 + index,
      media_type: "image/png",
    })),
    content_digest: `sha256:${"e".repeat(64)}`,
  };
}

const productionEligibility: StandardNativeEligibilityV5 = {
  schema_version: 5,
  source_type: "LIVE",
  source_manifest_schema_version: 5,
  capture_state: "committed",
  capture_committed: true,
  capture_healthy: true,
  full_device_span: true,
  validity_aware: true,
  automatic_eligible: true,
  explicit_eligible: true,
  promotion_allowed: true,
  evidence_only: false,
  dwell_class: "mixed_2p5_10",
  tuning_branch: "same",
  legs: [{
    schema_version: 5,
    stream_id: "stream-0",
    radio_id: "radio0",
    profile_name: "production-low",
    profile_revision_digest: `sha256:${"1".repeat(64)}`,
    receiver_ids: [0, 1],
    gain_controller_mode: "tandem_auto",
    gain_controller_request_digest: `sha256:${"2".repeat(64)}`,
    starlink_channel: 2,
    starlink_edge: "lower",
    sample_rate_hz: 2_500_000,
    rf_bandwidth_hz: 2_500_000,
    tuned_center_frequency_hz: 1_210_000_000,
    pilot_if_center_frequency_hz: 1_209_687_500,
    channel_if_start_hz: 1_205_000_000,
    channel_if_stop_hz: 1_445_000_000,
    captured_if_start_hz: 1_208_750_000,
    captured_if_stop_hz: 1_211_250_000,
    logical_sample_count: 150_000_000,
    validity_inventory_digest: `sha256:${"3".repeat(64)}`,
    timeline_digest: `sha256:${"4".repeat(64)}`,
    metadata_abi_version: 3,
  }, {
    schema_version: 5,
    stream_id: "stream-1",
    radio_id: "radio1",
    profile_name: "production-high",
    profile_revision_digest: `sha256:${"5".repeat(64)}`,
    receiver_ids: [0],
    gain_controller_mode: "tandem_auto",
    gain_controller_request_digest: `sha256:${"2".repeat(64)}`,
    starlink_channel: 2,
    starlink_edge: "lower",
    sample_rate_hz: 10_000_000,
    rf_bandwidth_hz: 10_000_000,
    tuned_center_frequency_hz: 1_210_000_000,
    pilot_if_center_frequency_hz: 1_209_687_500,
    channel_if_start_hz: 1_205_000_000,
    channel_if_stop_hz: 1_445_000_000,
    captured_if_start_hz: 1_205_000_000,
    captured_if_stop_hz: 1_215_000_000,
    logical_sample_count: 600_000_000,
    validity_inventory_digest: `sha256:${"6".repeat(64)}`,
    timeline_digest: `sha256:${"7".repeat(64)}`,
    metadata_abi_version: 3,
  }],
  scheduled_intent_digest: `sha256:${"8".repeat(64)}`,
  capture_plan_digest: `sha256:${"9".repeat(64)}`,
  capture_hardware_binding_digest: `sha256:${"a".repeat(64)}`,
  pipeline_definition_id: `sha256:${"b".repeat(64)}`,
  promotion_authority_digest: `sha256:${"c".repeat(64)}`,
  resampled: false,
  reason: "Promoted reviewed production Standard-native capture is Current",
};

function productionSubject(
  base: StandardNativeSubjectSummaryV3,
): StandardNativeSubjectSummaryV5 {
  return { ...base, schema_version: 5, eligibility: productionEligibility };
}

const productionPaths = paths.slice(0, 3);
const productionPathSubjects = productionPaths.map((path, index) => productionSubject(nativeSubject(
  path.subject_id,
  `${path.radio_label} ${path.receiver_label}`,
  "receiver_path",
  [path],
  nativeTerminal(index < 2 ? 150 : 600, index < 2 ? 150 : 600, 1, 4),
)));
const productionRadio0 = productionSubject(nativeSubject(
  "radio:stream-0", "Radio0", "radio", productionPaths.slice(0, 2), nativeTerminal(300, 300, 2, 8),
));
const productionRadio1 = productionSubject(nativeSubject(
  "radio:stream-1", "Radio1", "radio", productionPaths.slice(2), nativeTerminal(600, 600, 1, 4),
));
const productionPair: StandardNativeSubjectSummaryV5 = {
  ...productionSubject(nativeSubject(
    "pair:stream-0:stream-1",
    "Paired Radio0 + Radio1",
    "radio",
    productionPaths,
    nativeTerminal(900, 900, 3, 12),
  )),
  subject_kind: "paired",
  child_subject_ids: [productionRadio0.subject_id, productionRadio1.subject_id],
};
const productionHierarchy: StandardNativeSubjectHierarchyV5 = {
  schema_version: 5,
  session_id: "T1",
  source_type: "LIVE",
  eligibility: productionEligibility,
  generated_at: "2026-08-29T13:30:00Z",
  rows: [productionPair, productionRadio0, productionRadio1],
};
const productionEvidence = productionPathSubjects.map((subject) => ({
  schema_version: 3 as const,
  receiver_path: subject.receiver_paths[0],
  terminal: subject.terminal,
  declared_seconds: 60,
  valid_seconds: 60,
  continuity_segment_count: 1,
  continuity_boundary_count: 0,
  invalid_zero_fill_excluded: true as const,
}));
const productionDetail: StandardNativeSubjectDetailV5 = {
  ...nativeDetail,
  schema_version: 5,
  subject: productionPair,
  receiver_path_expansions: productionPathSubjects,
  receiver_path_evidence: productionEvidence,
};

function productionArtifactInventory(): StandardNativePngArtifactInventoryV6 {
  const v5 = mixedArtifactInventory();
  return {
    ...v5,
    schema_version: 6,
    subject_id: productionPair.subject_id,
    sample_rates_hz: [2_500_000, 10_000_000],
    artifacts: v5.artifacts.map((artifact) => ({
      ...artifact,
      href: artifact.href.replace(encodeURIComponent(mixedPair.subject_id), encodeURIComponent(productionPair.subject_id)),
    })),
  };
}

function productionPhaseArtifactInventory(): StandardNativePngArtifactInventoryV7 {
  return {
    ...productionArtifactInventory(),
    schema_version: 7,
  };
}

function phaseArtifactInventory(): StandardNativePngArtifactInventoryV7 {
  const { sample_rate_hz, ...legacy } = nativeArtifactInventory(nativePathDetail);
  return {
    ...legacy,
    schema_version: 7,
    sample_rates_hz: [sample_rate_hz],
    artifacts: legacy.artifacts.map((artifact) => {
      if (artifact.name === "pilot-doppler") {
        return {
          ...artifact,
          description: "Independent local Doppler and held-out adjacent phase evidence",
          product_schema_version: 4,
        };
      }
      if (artifact.name === "pilot-carrier-tracking") {
        return {
          ...artifact,
          label: "Held-out adjacent carrier-phase trackability",
          description: "Prefix-trained modulo-pi nuisance and later one-step innovations",
          product_schema_version: 4,
        };
      }
      if (artifact.name === "pilot-segment-rates") {
        return {
          ...artifact,
          description: "Independent direct rates remain separate across continuity segments",
          product_schema_version: 4,
        };
      }
      return artifact;
    }),
  };
}

const productionPlot: StandardNativePlotViewV5 = {
  schema_version: 5,
  session_id: "T1",
  subject_id: productionPair.subject_id,
  view_kind: "quality",
  state: "unavailable",
  time_domain: domain,
  receiver_path_ids: productionPaths.map((path) => path.path_id),
  sample_rates_hz: [2_500_000, 10_000_000],
  source_proof: {
    schema_version: 3,
    run_manifest_digest: `sha256:${"d".repeat(64)}`,
    products: [],
    content_digest: `sha256:${"e".repeat(64)}`,
  },
  source_point_count: 0,
  returned_point_count: 0,
  truncated: false,
  metric_series: [],
  frequency_axes: [],
  waterfall_tiles: [],
  trajectories: [],
  reason: "No sealed evidence for this view",
  projection_digest: `sha256:${"f".repeat(64)}`,
};
const nativeWaterfall: StandardNativePlotViewV3 = {
  schema_version: 3,
  session_id: "T1",
  subject_id: nativeRadio.subject_id,
  view_kind: "waterfall",
  state: "partial",
  time_domain: domain,
  receiver_path_ids: nativePaths.map((path) => path.path_id),
  sample_rate_hz: 3_000_000,
  source_proof: {
    schema_version: 3,
    run_manifest_digest: `sha256:${"7".repeat(64)}`,
    products: nativePaths.map((path, index) => ({
      schema_version: 3,
      product_id: index + 1,
      scope_key: `scope:${path.path_id}`,
      kind: "standard.numerical-waterfall",
      product_schema_version: 3,
      digest: `sha256:${String(index + 8).repeat(64)}`,
    })),
    content_digest: `sha256:${"a".repeat(64)}`,
  },
  source_point_count: 2,
  returned_point_count: 2,
  truncated: false,
  metric_series: [],
  frequency_bin_centers_hz: [-1_000, 1_000],
  waterfall_tiles: [{
    schema_version: 3,
    receiver_path_id: nativePaths[0].path_id,
    time_bin: 0,
    time_start_s: 0,
    time_stop_s: 0.5,
    sample_start: 0,
    sample_stop: 1_500_000,
    transform_count: 1,
    valid: true,
    power_dbfs: [-80, -70],
  }, {
    schema_version: 3,
    receiver_path_id: nativePaths[1].path_id,
    time_bin: 0,
    time_start_s: 0,
    time_stop_s: 0.5,
    sample_start: 0,
    sample_stop: 1_500_000,
    transform_count: 0,
    valid: false,
    power_dbfs: [null, null],
  }],
  trajectories: [],
  reason: "Validity-aware native evidence projected without resampling",
  projection_digest: `sha256:${"b".repeat(64)}`,
};

function metricView(kind: StandardViewKindV2): StandardPlotViewV2 {
  return {
    schema_version: 2, session_id: "T1", subject_id: pair.subject_id, view_kind: kind,
    state: "available", time_domain: domain, source_point_count: 3, returned_point_count: 3,
    receiver_path_ids: paths.map((path) => path.path_id),
    horizontal_axis: kind === "waterfall"
      ? { axis_id: "frequency_hz", label: "Baseband frequency", unit: "Hz", full_source_min: 200000, full_source_max: 300000 }
      : { axis_id: "time", label: "Shared elapsed time", unit: "s", full_source_min: 0, full_source_max: 60 },
    vertical_axis: kind === "waterfall"
      ? { axis_id: "time", label: "Shared elapsed time", unit: "s", full_source_min: 0, full_source_max: 60 }
      : { axis_id: "metric_value", label: kind, unit: "response", full_source_min: 0, full_source_max: 1 },
    color_axis: kind === "waterfall"
      ? { axis_id: "power_db", label: "Power", unit: "dB", full_source_min: -100, full_source_max: -20 }
      : null,
    source_extrema: {
      schema_version: 2,
      source_artifact_digest: "a".repeat(64),
      source_content_digest: "b".repeat(64),
      source_point_count: 3,
      axes: kind === "waterfall"
        ? [
          { axis_id: "frequency_hz", source_min: 200000, source_max: 300000 },
          { axis_id: "power_db", source_min: -100, source_max: -20 },
        ]
        : [{ axis_id: "metric_value", source_min: 0, source_max: 1 }],
      lanes: [{
        receiver_path_id: "radio0:rx0",
        source_point_count: 3,
        axes: kind === "waterfall"
          ? [
            { axis_id: "frequency_hz", source_min: 200000, source_max: 300000 },
            { axis_id: "power_db", source_min: -100, source_max: -20 },
          ]
          : [{ axis_id: "metric_value", source_min: 0, source_max: 1 }],
      }],
      canonical_digest: "c".repeat(64),
    },
    truncated: false,
    series: kind === "waterfall" || kind === "cfo_trajectory" ? [] : [{
      series_id: `${kind}:rx0`, receiver_path_id: "radio0:rx0", label: kind,
      unit: "response", source_point_count: 3,
      points: [{ time_s: 0, value: .1 }, { time_s: 30, value: .3 }, { time_s: 60, value: .2 }],
      truncated: false, source_min: .1, source_max: .3,
    }],
    waterfall_cells: kind === "waterfall" ? [
      { receiver_path_id: "radio0:rx0", time_s: 0, frequency_hz: 250000, power_db: -70 },
      { receiver_path_id: "radio0:rx1", time_s: 30, frequency_hz: 255000, power_db: -60 },
      { receiver_path_id: "radio1:rx0", time_s: 60, frequency_hz: 260000, power_db: -50 },
    ] : [],
    cfo_observations: [], trajectory_curves: [], reason: "bounded fixture",
  };
}

afterEach(() => vi.restoreAllMocks());

test("renders native Current and registered PNGs without a waterfall cell table", async () => {
  const requested: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    requested.push(url);
    if (url.includes("/artifacts?")) {
      const pathSelected = url.includes(encodeURIComponent(nativePathSubjects[0].subject_id));
      return new Response(JSON.stringify(nativeArtifactInventory(
        pathSelected ? nativePathDetail : nativeDetail,
      )), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("/views/waterfall?")) {
      const pathSelected = url.includes(encodeURIComponent(nativePathSubjects[0].subject_id));
      const view = pathSelected ? {
        ...nativeWaterfall,
        subject_id: nativePathSubjects[0].subject_id,
        receiver_path_ids: [nativePaths[0].path_id],
        source_proof: {
          ...nativeWaterfall.source_proof,
          products: nativeWaterfall.source_proof.products.slice(0, 1),
        },
        source_point_count: 1,
        returned_point_count: 1,
        waterfall_tiles: nativeWaterfall.waterfall_tiles.slice(0, 1),
      } : nativeWaterfall;
      return new Response(JSON.stringify(view), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes(encodeURIComponent(nativePathSubjects[0].subject_id))) {
      return new Response(JSON.stringify(nativePathDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes(encodeURIComponent(nativeRadio.subject_id))) {
      return new Response(JSON.stringify(nativeDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(nativeHierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest={false} />);

  expect(await screen.findByText("Standard native analysis")).toBeInTheDocument();
  expect(screen.getByText("STANDARD · NATIVE · 3.0 MS/s")).toBeInTheDocument();
  expect(screen.getByText("LIVE · CURRENT · PARTIAL COVERAGE")).toBeInTheDocument();
  const summary = await screen.findByRole("region", { name: "Native validity and scientific summary" });
  expect(within(summary).getByText("90.000% valid coverage")).toBeInTheDocument();
  expect(within(summary).getByText("SCIENTIFIC DISPOSITION")).toBeInTheDocument();
  expect(within(summary).getAllByText("insufficient").length).toBeGreaterThan(0);
  expect(within(summary).getByText("VALID-SAMPLE SUFFICIENT STATISTICS")).toBeInTheDocument();
  expect(within(summary).getByText("No cross-gap operation")).toBeInTheDocument();

  const registered = screen.getByRole("region", { name: "Registered native image artifacts" });
  await waitFor(() => expect(within(registered).getAllByRole("img")).toHaveLength(5));
  expect(within(registered).getByRole("img", { name: /Waterfall/ })).toHaveAttribute(
    "src",
    nativeArtifactInventory(nativeDetail).artifacts[0].href,
  );
  expect(screen.getByRole("img", { name: /De-aliased/ })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Final replay/ })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Native waterfall validity" }))
    .not.toBeInTheDocument();
  expect(requested.every((url) => !url.includes("/views/waterfall?"))).toBe(true);
  expect(requested.every((url) => !url.includes("track-gates")
    && !url.includes("replay-audit")
    && !url.includes("standard-investigations"))).toBe(true);

  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  fireEvent.click(within(tabs).getByRole("button", { name: /Radio0 RX0/ }));
  const alternate = await screen.findByRole("img", { name: /Alternate Hough CFO candidates/ });
  expect(alternate).toHaveAttribute(
    "src",
    `/api/v2/recordings/T1/standard-subjects/${encodeURIComponent(nativePathSubjects[0].subject_id)}/artifacts/cfo-alternate.png`,
  );
  await waitFor(() => expect(screen.getByRole("region", { name: "Registered native image artifacts" })
    .querySelectorAll("img")).toHaveLength(11));
  expect(screen.getByRole("img", { name: /Pilot Doppler qualification overview/ }))
    .toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Doppler rates across/ })).toBeInTheDocument();
});

test("renders mixed 2.5/5 Current with sealed same-channel RF passbands and paired PNGs", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/artifacts?")) {
      return new Response(JSON.stringify(mixedArtifactInventory()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes(encodeURIComponent(mixedPair.subject_id))) {
      return new Response(JSON.stringify(mixedDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(mixedHierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest={false} />);

  expect(await screen.findByText("Standard native analysis")).toBeInTheDocument();
  expect(screen.getByText("STANDARD · NATIVE · MIXED 2.5 + 5.0 MS/s")).toBeInTheDocument();
  const authority = await screen.findByRole("region", { name: "Mixed-rate RF coverage authority" });
  expect(within(authority).getAllByText(/Channel 3 lower/)).toHaveLength(2);
  expect(within(authority).getByText(/analog BW 2.5000 MHz/)).toBeInTheDocument();
  expect(within(authority).getByText(/analog BW 5.0000 MHz/)).toBeInTheDocument();
  expect(within(authority).getAllByText(/pilot 1459.6875 MHz IF/)).toHaveLength(2);
  expect(within(authority).getByText(/1458.4375 MHz–1460.9375 MHz IF/)).toBeInTheDocument();
  expect(within(authority).getByText(/1457.1875 MHz–1462.1875 MHz IF/)).toBeInTheDocument();
  const gallery = await screen.findByRole("region", { name: "Registered native image artifacts" });
  await waitFor(() => expect(within(gallery).getAllByRole("img")).toHaveLength(5));
  expect(screen.queryByRole("region", { name: "Native waterfall validity" }))
    .not.toBeInTheDocument();
});

test("renders the complete production V5 hierarchy/detail with its V6 PNG inventory", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/artifacts?")) {
      return new Response(JSON.stringify(productionArtifactInventory()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes(encodeURIComponent(productionPair.subject_id))) {
      return new Response(JSON.stringify(productionDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(productionHierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest={false} />);

  expect(await screen.findByText("Standard native analysis")).toBeInTheDocument();
  expect(screen.getByText("STANDARD · NATIVE · MIXED 2P5 10 2.5 + 10.0 MS/s"))
    .toBeInTheDocument();
  const authority = await screen.findByRole("region", { name: "Production RF coverage authority" });
  expect(within(authority).getByText(/mixed 2p5 10 · same tuning/i)).toBeInTheDocument();
  expect(within(authority).getByText(/RX0 \+ RX1 · tandem auto · metadata ABI 3/)).toBeInTheDocument();
  expect(within(authority).getByText(/RX0 · tandem auto · metadata ABI 3/)).toBeInTheDocument();
  const gallery = await screen.findByRole("region", { name: "Registered native image artifacts" });
  await waitFor(() => expect(within(gallery).getAllByRole("img")).toHaveLength(5));

  expect(parseStandardSubjectHierarchy(productionHierarchy).schema_version).toBe(5);
  expect(parseStandardSubjectDetail(productionDetail).schema_version).toBe(5);
  expect(parseStandardPlotView(productionPlot).schema_version).toBe(5);
  expect(parseStandardNativePngArtifactInventory(productionArtifactInventory()).schema_version)
    .toBe(6);
});

test("renders every registered PNG for production V5 detail with a V7 inventory", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/artifacts?")) {
      return new Response(JSON.stringify(productionPhaseArtifactInventory()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes(encodeURIComponent(productionPair.subject_id))) {
      return new Response(JSON.stringify(productionDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(productionHierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest={false} />);

  const gallery = await screen.findByRole("region", {
    name: "Registered native image artifacts",
  });
  await waitFor(() => expect(within(gallery).getAllByRole("img")).toHaveLength(5));
  expect(within(gallery).getByRole("img", { name: /Pilot detector comparison/ }))
    .toBeInTheDocument();
  expect(within(gallery).getByRole("img", { name: /Final replay/ }))
    .toBeInTheDocument();
  expect(parseStandardNativePngArtifactInventory(productionPhaseArtifactInventory()).schema_version)
    .toBe(7);
});

test.each([
  ["both_2p5", 2_500_000, 2_500_000],
  ["both_5", 5_000_000, 5_000_000],
  ["mixed_2p5_5", 2_500_000, 5_000_000],
  ["mixed_2p5_10", 2_500_000, 10_000_000],
  ["mixed_2p5_15", 2_500_000, 15_000_000],
  ["mixed_2p5_20", 2_500_000, 20_000_000],
] as const)("accepts exact production dwell geometry %s", (dwellClass, lowRate, highRate) => {
  const document = structuredClone(productionHierarchy) as unknown as Record<string, unknown>;
  const authorities = [document.eligibility, ...(document.rows as Array<Record<string, unknown>>)
    .map((row) => row.eligibility)] as Array<Record<string, unknown>>;
  authorities.forEach((authority) => {
    authority.dwell_class = dwellClass;
    authority.tuning_branch = dwellClass.startsWith("mixed_") ? "same" : "independent";
    const legs = authority.legs as Array<Record<string, unknown>>;
    [lowRate, highRate].forEach((rate, index) => {
      const leg = legs[index];
      leg.sample_rate_hz = rate;
      leg.rf_bandwidth_hz = rate;
      leg.captured_if_start_hz = 1_210_000_000 - rate / 2;
      leg.captured_if_stop_hz = 1_210_000_000 + rate / 2;
      leg.channel_if_start_hz = 1_195_000_000;
      leg.logical_sample_count = rate * 60;
      leg.receiver_ids = dwellClass.startsWith("mixed_") && rate > 5_000_000
        ? [index]
        : [0, 1];
    });
  });
  expect(parseStandardSubjectHierarchy(document).schema_version).toBe(5);
});

test.each([
  ["crossed radio order", (document: Record<string, unknown>) => {
    const eligibility = document.eligibility as Record<string, unknown>;
    const legs = eligibility.legs as Array<Record<string, unknown>>;
    legs[0].stream_id = "stream-9";
  }],
  ["wrong high-rate receiver geometry", (document: Record<string, unknown>) => {
    const eligibility = document.eligibility as Record<string, unknown>;
    const legs = eligibility.legs as Array<Record<string, unknown>>;
    legs[1].receiver_ids = [0, 1];
  }],
  ["missing authority digest", (document: Record<string, unknown>) => {
    const eligibility = document.eligibility as Record<string, unknown>;
    delete eligibility.capture_plan_digest;
  }],
] as const)("rejects production V5 %s", (_name, mutate) => {
  const document = structuredClone(productionHierarchy) as unknown as Record<string, unknown>;
  mutate(document);
  expect(() => parseStandardSubjectHierarchy(document)).toThrow(/contract is invalid/);
});

test("accepts additive phase inventory and rejects future native presentation versions", () => {
  const phase = parseStandardNativePngArtifactInventory(phaseArtifactInventory());
  expect(phase.schema_version).toBe(7);
  expect(phase.artifacts.filter((item) => item.name.startsWith("pilot-")).map(
    (item) => item.product_schema_version,
  )).toEqual([2, 4, 4, 4]);
  expect(() => parseStandardSubjectHierarchy({ ...productionHierarchy, schema_version: 6 }))
    .toThrow(/expected 2, 3, 4, or 5/);
  expect(() => parseStandardNativePngArtifactInventory({
    ...productionArtifactInventory(),
    schema_version: 8,
  })).toThrow(/expected one of 4, 5, 6, 7/);
});

test("rejects mixed Current when sealed RF bandwidth does not match its native sample rate", () => {
  const crossed = structuredClone(mixedHierarchy) as unknown as Record<string, unknown>;
  const eligibility = crossed.eligibility as Record<string, unknown>;
  const legs = eligibility.legs as Array<Record<string, unknown>>;
  legs[1].rf_bandwidth_hz = 2_500_000;
  expect(() => parseStandardSubjectHierarchy(crossed)).toThrow(
    /RF bandwidth differs from native sample rate/,
  );
});

test("keeps both radio subjects reachable beside all paths and the paired subject", async () => {
  const allPathSubjects = paths.map((path, index) => nativeSubject(
    path.subject_id,
    `${path.radio_label} ${path.receiver_label}`,
    "receiver_path",
    [path],
    nativeTerminal(50, 45, 1, index + 2),
  ));
  const radio1 = nativeSubject(
    "radio:radio1",
    "Radio1",
    "radio",
    paths.slice(2),
    nativeTerminal(100, 90, 2, 4),
  );
  const paired: StandardNativeSubjectSummaryV3 = {
    ...nativeRadio,
    subject_id: "pair:radio0:radio1",
    subject_kind: "paired",
    label: "Paired Radio0 + Radio1",
    receiver_paths: paths,
    expected_path_count: 4,
    completed_path_count: 4,
    child_subject_ids: [nativeRadio.subject_id, radio1.subject_id],
    terminal: nativeTerminal(200, 180, 4, 8),
  };
  const allEvidence = allPathSubjects.map((subject) => ({
    ...nativeEvidence[0],
    receiver_path: subject.receiver_paths[0],
    terminal: subject.terminal,
  }));
  const pairedDetail: StandardNativeSubjectDetailV3 = {
    ...nativeDetail,
    subject: paired,
    receiver_path_expansions: allPathSubjects,
    receiver_path_evidence: allEvidence,
  };
  const radio1Detail: StandardNativeSubjectDetailV3 = {
    ...nativeDetail,
    subject: radio1,
    receiver_path_expansions: allPathSubjects.slice(2),
    receiver_path_evidence: allEvidence.slice(2),
  };
  const completeHierarchy: StandardNativeSubjectHierarchyV3 = {
    ...nativeHierarchy,
    rows: [paired, nativeRadio, radio1],
  };
  const details = new Map<string, StandardNativeSubjectDetailV3>([
    [paired.subject_id, pairedDetail],
    [nativeRadio.subject_id, nativeDetail],
    [radio1.subject_id, radio1Detail],
    ...allPathSubjects.map((subject, index): [string, StandardNativeSubjectDetailV3] => [
      subject.subject_id,
      {
        ...nativeDetail,
        subject,
        receiver_path_expansions: [subject],
        receiver_path_evidence: [allEvidence[index]],
      },
    ]),
  ]);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const selected = [...details.entries()].find(([subjectId]) =>
      url.includes(encodeURIComponent(subjectId)))?.[1];
    if (url.includes("/artifacts?")) {
      if (!selected) return new Response(null, { status: 404 });
      return new Response(JSON.stringify(nativeArtifactInventory(selected)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (selected) {
      return new Response(JSON.stringify(selected), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(completeHierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest={false} />);

  expect(await screen.findByText("Standard native analysis")).toBeInTheDocument();
  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  await waitFor(() => expect(within(tabs).getAllByRole("button")).toHaveLength(7));
  expect(within(tabs).getByRole("button", { name: /Radio0 current/ })).toBeInTheDocument();
  expect(within(tabs).getByRole("button", { name: /Radio1 current/ })).toBeInTheDocument();
  expect(within(tabs).getByRole("button", { name: /Combined 4-path/ })).toBeInTheDocument();

  fireEvent.click(within(tabs).getByRole("button", { name: /Radio1 current/ }));
  const gallery = await screen.findByRole("region", { name: "Registered native image artifacts" });
  await waitFor(() => expect(within(gallery).getAllByRole("img")).toHaveLength(5));
  expect(within(tabs).getAllByRole("button")).toHaveLength(7);
});

test("strictly rejects crossed V3-only fields and measured values in a gap tile", () => {
  const crossedHierarchy = structuredClone(nativeHierarchy) as unknown as Record<string, unknown>;
  const rows = crossedHierarchy.rows as Array<Record<string, unknown>>;
  rows[0].state_reasons = [];
  expect(() => parseStandardSubjectHierarchy(crossedHierarchy)).toThrow(/unexpected field.*state_reasons/);

  const crossedWaterfall = structuredClone(nativeWaterfall);
  crossedWaterfall.waterfall_tiles[1].power_dbfs[0] = 0;
  expect(() => parseStandardPlotView(crossedWaterfall)).toThrow(
    /missing waterfall power must be null, never zero-filled measurement/,
  );
});

test("rejects crossed eligibility reason truth before rendering subjects", async () => {
  const crossedHierarchy: StandardSubjectHierarchyV2 = {
    ...hierarchy,
    eligibility: {
      ...hierarchy.eligibility,
      reason: "Committed ordinary LIVE capture is Standard eligible",
    },
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(
    JSON.stringify(crossedHierarchy),
    { status: 200, headers: { "Content-Type": "application/json" } },
  )));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Standard eligibility reason does not match its truth projection",
  );
});

test("rejects current subjects carrying stale-coded reasons", async () => {
  const currentWithStaleReason: StandardSubjectSummaryV2 = {
    ...pair,
    state: "current",
    state_reasons: [{
      code: "product_unavailable",
      message: "Product is unavailable",
      affected_stage_keys: [],
      affected_subject_ids: [],
    }],
  };
  const crossedHierarchy: StandardSubjectHierarchyV2 = {
    ...hierarchy,
    rows: [currentWithStaleReason, ...hierarchy.rows.slice(1)],
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(
    JSON.stringify(crossedHierarchy),
    { status: 200, headers: { "Content-Type": "application/json" } },
  )));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Standard subject state and stale reasons are incompatible",
  );
});

test("shows four independent receiver tabs plus a combined PNG gallery", async () => {
  const pathDetail = (index: number): StandardSubjectDetailV2 => ({
    ...detail,
    subject: detail.receiver_path_expansions[index],
    receiver_path_expansions: [detail.receiver_path_expansions[index]],
    receiver_path_evidence: [detail.receiver_path_evidence[index]],
  });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/standard-investigations")) return new Response(null, { status: 404 });
    if (url.includes("/track-gates")) return new Response(JSON.stringify({
      schema_version: 1, session_id: "T1", subject_id: pair.subject_id,
      stages: [{
        stage_key: "trajectory-fit", label: "Original Hough segments",
        description: "Accepted initial and residual-Hough line segments before robust refinement.",
        source_track_count: 1, truncated: false, limitation: null,
        rows: [{
          receiver_path_id: "radio0:rx0", track_id: `sha256:${"1".repeat(64)}`,
          disposition: "passed", reason: "retained in the immutable fitted-trajectory bank",
          gates: [
            { gate_key: "start-time", label: "Start", value: "1", criterion: "persisted segment boundary (s)", verdict: "audit" },
            { gate_key: "end-time", label: "End", value: "5", criterion: "persisted segment boundary (s)", verdict: "audit" },
            { gate_key: "slope", label: "Slope", value: "-5248.57", criterion: "Hz/s; original Hough segment coefficient", verdict: "audit" },
            { gate_key: "support", label: "Support", value: "41", criterion: "retained fit support", verdict: "pass" },
          ],
        }],
      }, {
        stage_key: "dealias-refinement", label: "Huber residual refinement",
        description: "Fixed-membership MAD-scaled Huber IRLS with c=1.345.",
        source_track_count: 1, truncated: false, limitation: null,
        rows: [{
          receiver_path_id: "radio0:rx0", track_id: `sha256:${"1".repeat(64)}`,
          disposition: "retained", reason: "one Huber-refined output for this Hough seed",
          gates: [
            { gate_key: "huber-slope", label: "Huber slope", value: "-5199.2", criterion: "MAD-scaled Huber IRLS coefficient (Hz/s)", verdict: "audit" },
            { gate_key: "huber-mad-scale", label: "Huber MAD scale", value: "100", criterion: "max(100 Hz, 1.4826 × residual MAD)", verdict: "audit" },
            { gate_key: "huber-convergence", label: "Huber converged", value: "yes", criterion: "MAD-scaled Huber IRLS, c=1.345", verdict: "pass" },
          ],
        }],
      }, {
        stage_key: "lift-replay", label: "Lift replay gates",
        description: "Each lift is classified from persisted replay evidence.",
        source_track_count: 1, truncated: false, limitation: null,
        rows: [{
          receiver_path_id: "radio0:rx0", track_id: `sha256:${"2".repeat(64)}:0`,
          disposition: "passed", reason: "geometry and replay coverage passed; corrected-margin metrics are audit-only",
          gates: [
            { gate_key: "probe-count", label: "Replay probes", value: "304", criterion: "≥ 20", verdict: "pass" },
            { gate_key: "absolute-margin", label: "Corrected margin", value: "0.005088", criterion: "audit only; never vetoes V4", verdict: "audit" },
            { gate_key: "harmful-blocks", label: "Harmful blocks", value: "2 (run 1)", criterion: "audit only; never vetoes V4", verdict: "audit" },
          ],
        }],
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } });
    if (url.includes("/replay-audit")) return new Response(JSON.stringify({
      schema_version: 1, session_id: "T1", subject_id: pair.subject_id,
      source_row_count: 1, truncated: false,
      rows: [{
        receiver_path_id: "radio0:rx0", branch_id: `sha256:${"2".repeat(64)}`,
        alias_index: 0, tier: "automatic", automatic_correction_eligible: true,
        geometry_display_eligible: true, evaluated_probe_count: 304,
        evaluated_block_count: 9, block_coverage_ratio: 1,
        median_block_corrected_margin: 0.005088, harmful_block_count: 2,
        maximum_consecutive_harmful_blocks: 1,
        reasons: ["geometry and replay coverage passed; corrected-margin metrics are audit-only"],
        retained_in_final: true,
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } });
    let body: StandardSubjectHierarchyV2 | StandardSubjectDetailV2 = hierarchy;
    if (url.includes("pair%3Aradio0%3Aradio1")) body = detail;
    if (url.includes("path%3Aradio0%3Arx0")) body = pathDetail(0);
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  expect(within(tabs).getAllByRole("button")).toHaveLength(5);
  for (const label of ["Radio0 RX0", "Radio0 RX1", "Radio1 RX0", "Radio1 RX1"]) {
    expect(within(tabs).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
  }
  expect(within(tabs).getByRole("button", { name: /Combined 4-path/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  const originalSegments = screen.getByRole("table", { name: "Original Hough segments table" });
  expect(originalSegments).toHaveTextContent("-5248.57");
  expect(originalSegments).toHaveTextContent("41");
  const finalSegments = screen.getByRole("table", { name: "Huber residual segments (final) table" });
  expect(finalSegments).toHaveTextContent("-5199.2");
  expect(finalSegments).toHaveTextContent("Huber MAD scale");
  expect(finalSegments).toHaveTextContent("c=1.345");
  expect(screen.queryByRole("table", { name: "Tracking detections" })).not.toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Alternate CFO line candidates" })).not.toBeInTheDocument();
  const gateTable = screen.getByRole("table", { name: "Lift replay gates table" });
  expect(gateTable).toHaveTextContent("Replay probes");
  expect(gateTable).toHaveTextContent("304");
  expect(gateTable).toHaveTextContent("Corrected margin");
  expect(gateTable).toHaveTextContent("passed");
  expect(gateTable).toHaveTextContent("audit only; never vetoes V4");
  expect(screen.queryByRole("table", { name: "CFO replay audit metrics" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(9);
  expect(screen.queryByRole("img", { name: /Known-pilot QAM/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /Power over time/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /Signal quality/ })).not.toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Waterfall.*Paired/ })).toHaveAttribute(
    "src",
    expect.stringContaining("/views/waterfall.png?"),
  );
  expect(screen.getAllByRole("link", { name: "Open PNG" })).toHaveLength(9);
  expect(screen.getByRole("img", { name: /De-aliased CFO trajectories.*Paired/ })).toHaveAttribute(
    "src",
    "/api/v2/recordings/T1/standard-subjects/pair%3Aradio0%3Aradio1/artifacts/cfo-dealiased.png",
  );
  expect(screen.getByRole("img", { name: /Final replay-classified CFO candidates.*Paired/ })).toHaveAttribute(
    "src",
    "/api/v2/recordings/T1/standard-subjects/pair%3Aradio0%3Aradio1/artifacts/cfo-final.png",
  );
  const pairedHough = screen.getByRole("region", {
    name: "Paired receiver-path Hough CFO candidates",
  });
  expect(within(pairedHough).getAllByRole("img")).toHaveLength(4);
  for (const path of paths) {
    expect(within(pairedHough).getByRole("img", {
      name: `Alternate Hough CFO candidates for ${path.radio_label} ${path.receiver_label}`,
    })).toHaveAttribute(
      "src",
      `/api/v2/recordings/T1/standard-subjects/${encodeURIComponent(path.subject_id)}/artifacts/cfo-alternate.png`,
    );
  }
  expect(within(pairedHough).getByText(/No joint or cross-radio Hough product is inferred/)).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /Alternate Hough.*Paired Radio/ })).not.toBeInTheDocument();
  expect(screen.getByText("frequency → · elapsed time ↓ · color = power")).toBeInTheDocument();

  fireEvent.click(within(tabs).getByRole("button", { name: /Radio0 RX0/ }));
  await waitFor(() => expect(screen.getByRole("img", { name: /Waterfall.*Radio0 RX0/ })).toHaveAttribute(
    "src",
    expect.stringContaining("path%3Aradio0%3Arx0/views/waterfall.png"),
  ));
});

test("uses only the independent Research API and PNG namespace on the Research tab", async () => {
  const requested: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    requested.push(url);
    const body = url.includes("pair%3Aradio0%3Aradio1") ? detail : hierarchy;
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest lane="research" />);

  expect(await screen.findByText("Research analysis image artifacts")).toBeInTheDocument();
  expect(requested.some((url) => url.includes("/research-subjects"))).toBe(true);
  expect(requested.every((url) => !url.includes("/standard-investigations"))).toBe(true);
  expect(await screen.findByRole("img", { name: /Waterfall/ })).toHaveAttribute(
    "src",
    expect.stringContaining("/research-subjects/"),
  );
  expect(screen.getByRole("img", { name: /Final replay-classified CFO candidates/ })).toHaveAttribute(
    "src",
    expect.stringContaining("/research-subjects/"),
  );
});

test("keeps research-only alternate lines out of the Standard tables while showing their PNG", async () => {
  const pathDetail: StandardSubjectDetailV2 = {
    ...detail,
    subject: detail.receiver_path_expansions[0],
    receiver_path_expansions: [detail.receiver_path_expansions[0]],
    receiver_path_evidence: [detail.receiver_path_evidence[0]],
    alternate_track_source_count: 1,
    alternate_tracks_truncated: false,
    alternate_tracks: [{
      receiver_path_id: "radio0:rx0", track_id: `sha256:${"d".repeat(64)}`,
      start_s: 1, end_s: 5, span_s: 4, support_count: 41, weighted_support: 82.5,
      slope_hz_per_s: -5248.57, acceleration_hz_per_s2: 0,
      intercept_mod_alias_hz: 43120, residual_rms_hz: 83.75,
      residual_max_hz: 190, maximum_gap_s: .25,
      confidence: "strong_geometry", status: "research_only",
    }],
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/standard-investigations")) return new Response(null, { status: 404 });
    const body = url.includes("path%3Aradio0%3Arx0")
      ? pathDetail
      : url.includes("pair%3Aradio0%3Aradio1") ? detail : hierarchy;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  fireEvent.click(within(tabs).getByRole("button", { name: /Radio0 RX0/ }));
  await waitFor(() => expect(screen.queryByRole("table", { name: "Alternate CFO line candidates" })).not.toBeInTheDocument());
  expect(screen.getByRole("img", { name: /Alternate Hough CFO candidates/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/cfo-alternate.png",
  );
  expect(screen.getByRole("img", { name: /Trajectory-conditioned replay accounting/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/trajectory-accounting.png",
  );
  expect(screen.getByRole("img", { name: /Pilot Doppler qualification overview/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/pilot-doppler.png",
  );
  expect(screen.getByRole("img", { name: /Frame CFO and carrier-rate tracking/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/pilot-carrier-tracking.png",
  );
  expect(screen.getByRole("img", { name: /Doppler rates across 50–75 ms segment regions/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/pilot-segment-rates.png",
  );
  expect(screen.getByRole("img", { name: /Independent 20 ms GLRT and local Doppler rate/ })).toHaveAttribute(
    "src", "/api/v2/recordings/T1/standard-subjects/path%3Aradio0%3Arx0/artifacts/full-capture-glrt20ms.png",
  );
});

test("shows original beside a widened upper-edge investigation for its exact path", async () => {
  const pathDetail: StandardSubjectDetailV2 = {
    ...detail,
    subject: detail.receiver_path_expansions[2],
    receiver_path_expansions: [detail.receiver_path_expansions[2]],
    receiver_path_evidence: [detail.receiver_path_evidence[2]],
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/standard-investigations")) {
      return new Response(JSON.stringify({
        schema_version: 1,
        session_id: "T1",
        title: "Original vs widened",
        status: "exploratory",
        candidate_only: true,
        specificity_claimed: false,
        payload_decoded: false,
        images: [{
          image_id: "radio1-rx0-wide",
          subject_id: "path:radio1:rx0",
          label: "Widened upper-edge search",
          analysis_variant: "wide-fine-upper-edge",
          relative_path: "wide.png",
          byte_size: 100,
          digest: `sha256:${"a".repeat(64)}`,
        }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.includes("path%3Aradio1%3Arx0")) {
      return new Response(JSON.stringify(pathDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("pair%3Aradio0%3Aradio1")) {
      return new Response(JSON.stringify(detail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(hierarchy), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  render(<StandardAnalysis sessionId="T1" includeTest />);
  const tabs = await screen.findByRole("navigation", { name: "Receiver path image tabs" });
  fireEvent.click(within(tabs).getByRole("button", { name: /Radio1 RX0/ }));
  const comparison = await screen.findByRole("region", {
    name: "Original and widened CFO search comparison",
  });
  expect(within(comparison).getByRole("img", { name: /Original Standard/ })).toHaveAttribute(
    "src",
    expect.stringContaining("/views/glrt64.png"),
  );
  expect(within(comparison).getByRole("img", { name: /Widened upper-edge/ })).toHaveAttribute(
    "src",
    "/api/v2/recordings/T1/standard-investigations/radio1-rx0-wide.png",
  );
  expect(within(comparison).getByText(/not the sealed current Standard result/)).toBeInTheDocument();
});
