import type {
  StandardNativeCoverageStatusV3,
  StandardNativePlotViewV3,
  StandardNativeScientificDispositionV3,
  StandardNativeSubjectDetailV3,
  StandardNativeSubjectHierarchyV3,
  StandardNativeSubjectSummaryV3,
  StandardPlotView,
  StandardPlotViewV2,
  StandardSubjectDetail,
  StandardSubjectDetailV2,
  StandardSubjectHierarchy,
  StandardSubjectHierarchyV2,
  StandardViewKindV2,
} from "./standard-contracts";

type JsonObject = Record<string, unknown>;

const viewKinds: StandardViewKindV2[] = [
  "quality",
  "power",
  "waterfall",
  "glrt64",
  "cfo_trajectory",
  "qam",
];
const coverageStates: StandardNativeCoverageStatusV3[] = [
  "complete",
  "partial_coverage",
  "insufficient_data",
];
const scienceStates: StandardNativeScientificDispositionV3[] = [
  "candidate",
  "no_candidate",
  "insufficient",
];
const sampleRates = [2_500_000, 3_000_000, 5_000_000] as const;

function fail(path: string, detail: string): never {
  throw new Error(`Standard ${path} contract is invalid: ${detail}`);
}

function object(value: unknown, path: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(path, "expected an object");
  }
  return value as JsonObject;
}

function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) fail(path, "expected an array");
  return value;
}

function string(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) fail(path, "expected a string");
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  if (value === null) return null;
  return string(value, path);
}

function number(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(path, "expected a finite number");
  return value;
}

function integer(value: unknown, path: string): number {
  const result = number(value, path);
  if (!Number.isInteger(result)) fail(path, "expected an integer");
  return result;
}

function nonnegativeInteger(value: unknown, path: string): number {
  const result = integer(value, path);
  if (result < 0) fail(path, "expected a nonnegative integer");
  return result;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(path, "expected a boolean");
  return value;
}

function oneOf<T extends string | number>(
  value: unknown,
  values: readonly T[],
  path: string,
): T {
  if (!values.includes(value as T)) fail(path, `expected one of ${values.join(", ")}`);
  return value as T;
}

function literal<T extends string | number | boolean | null>(
  value: unknown,
  expected: T,
  path: string,
): T {
  if (value !== expected) fail(path, `expected ${String(expected)}`);
  return expected;
}

function exactKeys(value: JsonObject, keys: readonly string[], path: string): void {
  const expected = new Set(keys);
  const unexpected = Object.keys(value).filter((key) => !expected.has(key));
  const missing = keys.filter((key) => !(key in value));
  if (unexpected.length || missing.length) {
    fail(
      path,
      [
        unexpected.length ? `unexpected field(s): ${unexpected.join(", ")}` : "",
        missing.length ? `missing field(s): ${missing.join(", ")}` : "",
      ].filter(Boolean).join("; "),
    );
  }
}

function assertStringArray(value: unknown, path: string): void {
  array(value, path).forEach((item, index) => string(item, `${path}[${index}]`));
}

function assertTimeDomain(value: unknown, path: string): void {
  const item = object(value, path);
  string(item.absolute_start_utc, `${path}.absolute_start_utc`);
  string(item.absolute_end_utc, `${path}.absolute_end_utc`);
  number(item.elapsed_start_s, `${path}.elapsed_start_s`);
  number(item.elapsed_end_s, `${path}.elapsed_end_s`);
  literal(item.time_unit, "s", `${path}.time_unit`);
  number(item.timing_uncertainty_s, `${path}.timing_uncertainty_s`);
}

function assertReceiverPath(value: unknown, path: string): void {
  const item = object(value, path);
  string(item.subject_id, `${path}.subject_id`);
  string(item.path_id, `${path}.path_id`);
  string(item.radio_id, `${path}.radio_id`);
  string(item.radio_label, `${path}.radio_label`);
  nonnegativeInteger(item.receiver_id, `${path}.receiver_id`);
  string(item.receiver_label, `${path}.receiver_label`);
  const scope = object(item.scope, `${path}.scope`);
  literal(scope.schema_version, 1, `${path}.scope.schema_version`);
  literal(scope.kind, "receiver_path", `${path}.scope.kind`);
  string(scope.session_id, `${path}.scope.session_id`);
  string(scope.stream_id, `${path}.scope.stream_id`);
  literal(scope.radio_id, null, `${path}.scope.radio_id`);
  nonnegativeInteger(scope.receiver_id, `${path}.scope.receiver_id`);
  literal(
    scope.synchronization_inventory_digest,
    null,
    `${path}.scope.synchronization_inventory_digest`,
  );
  string(item.scope_digest, `${path}.scope_digest`);
}

function assertReuse(value: unknown, path: string): void {
  const item = object(value, path);
  for (const key of [
    "computed_stage_count",
    "reused_stage_count",
    "recompute_stage_count",
    "blocked_stage_count",
  ]) nonnegativeInteger(item[key], `${path}.${key}`);
  assertStringArray(item.reused_from_run_ids, `${path}.reused_from_run_ids`);
  string(item.reason, `${path}.reason`);
}

function assertV2Eligibility(value: unknown, path: string): void {
  const item = object(value, path);
  oneOf(item.source_type, ["LIVE", "IMPORT", "TEST"], `${path}.source_type`);
  for (const key of [
    "capture_committed",
    "capture_healthy",
    "automatic_eligible",
    "explicit_eligible",
    "promotion_allowed",
    "evidence_only",
  ]) boolean(item[key], `${path}.${key}`);
  array(item.exclusion_tags, `${path}.exclusion_tags`).forEach((tag, index) =>
    oneOf(tag, ["QUALIFICATION", "CALIBRATION", "ACCEPTANCE"], `${path}.exclusion_tags[${index}]`));
  string(item.reason, `${path}.reason`);
}

function assertV2Subject(value: unknown, path: string): void {
  const item = object(value, path);
  string(item.subject_id, `${path}.subject_id`);
  string(item.session_id, `${path}.session_id`);
  oneOf(item.subject_kind, ["receiver_path", "radio", "paired"], `${path}.subject_kind`);
  string(item.label, `${path}.label`);
  boolean(item.derived, `${path}.derived`);
  array(item.receiver_paths, `${path}.receiver_paths`).forEach((row, index) =>
    assertReceiverPath(row, `${path}.receiver_paths[${index}]`));
  nonnegativeInteger(item.expected_path_count, `${path}.expected_path_count`);
  nonnegativeInteger(item.completed_path_count, `${path}.completed_path_count`);
  assertStringArray(item.child_subject_ids, `${path}.child_subject_ids`);
  oneOf(
    item.state,
    [
      "not_analyzed", "queued", "running", "blocked", "partial", "complete",
      "current", "stale", "failed", "unavailable",
    ],
    `${path}.state`,
  );
  boolean(item.ordinary_current, `${path}.ordinary_current`);
  array(item.state_reasons, `${path}.state_reasons`).forEach((reason, index) => {
    const row = object(reason, `${path}.state_reasons[${index}]`);
    if (row.code !== null) string(row.code, `${path}.state_reasons[${index}].code`);
    string(row.message, `${path}.state_reasons[${index}].message`);
    assertStringArray(row.affected_stage_keys, `${path}.state_reasons[${index}].affected_stage_keys`);
    assertStringArray(row.affected_subject_ids, `${path}.state_reasons[${index}].affected_subject_ids`);
  });
  if (item.pipeline_release !== null) object(item.pipeline_release, `${path}.pipeline_release`);
  string(item.desired_pipeline_release_id, `${path}.desired_pipeline_release_id`);
  assertReuse(item.reuse, `${path}.reuse`);
  assertV2Eligibility(item.eligibility, `${path}.eligibility`);
  literal(item.evidence_label, "candidate evidence only", `${path}.evidence_label`);
}

function assertStage(value: unknown, path: string): void {
  const item = object(value, path);
  string(item.stage_key, `${path}.stage_key`);
  string(item.subject_id, `${path}.subject_id`);
  oneOf(item.disposition, ["computed", "reused", "recompute", "blocked", "not_required"], `${path}.disposition`);
  if (item.runtime_seconds !== null) number(item.runtime_seconds, `${path}.runtime_seconds`);
  if (item.output_digest !== null) string(item.output_digest, `${path}.output_digest`);
  if (item.reused_from_run_id !== null) string(item.reused_from_run_id, `${path}.reused_from_run_id`);
  string(item.reason, `${path}.reason`);
}

function assertV2Detail(value: unknown): asserts value is StandardSubjectDetailV2 {
  const item = object(value, "subject detail V2");
  literal(item.schema_version, 2, "subject detail V2.schema_version");
  assertV2Subject(item.subject, "subject detail V2.subject");
  assertTimeDomain(item.time_domain, "subject detail V2.time_domain");
  array(item.receiver_path_expansions, "subject detail V2.receiver_path_expansions")
    .forEach((row, index) => assertV2Subject(row, `subject detail V2.receiver_path_expansions[${index}]`));
  array(item.receiver_path_evidence, "subject detail V2.receiver_path_evidence");
  nonnegativeInteger(item.stage_source_count, "subject detail V2.stage_source_count");
  array(item.stages, "subject detail V2.stages").forEach((row, index) =>
    assertStage(row, `subject detail V2.stages[${index}]`));
  boolean(item.stages_truncated, "subject detail V2.stages_truncated");
  nonnegativeInteger(item.trajectory_source_count, "subject detail V2.trajectory_source_count");
  array(item.trajectories, "subject detail V2.trajectories");
  boolean(item.trajectories_truncated, "subject detail V2.trajectories_truncated");
  array(item.views, "subject detail V2.views").forEach((view, index) => {
    const row = object(view, `subject detail V2.views[${index}]`);
    oneOf(row.view_kind, viewKinds, `subject detail V2.views[${index}].view_kind`);
    oneOf(row.state, ["available", "partial", "unavailable"], `subject detail V2.views[${index}].state`);
  });
  assertStringArray(item.limitations, "subject detail V2.limitations");
}

function assertV3Release(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "family", "authoritative_pipeline_release_id", "source_revision",
    "pipeline_definition_id", "graph_digest", "configuration_digest", "environment_digest",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  literal(item.family, "standard-native-v1", `${path}.family`);
  const revision = string(item.authoritative_pipeline_release_id, `${path}.authoritative_pipeline_release_id`);
  if (string(item.source_revision, `${path}.source_revision`) !== revision) {
    fail(path, "source revision differs from release authority");
  }
  for (const key of [
    "pipeline_definition_id", "graph_digest", "configuration_digest", "environment_digest",
  ]) string(item[key], `${path}.${key}`);
}

function assertV3Eligibility(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "source_type", "source_manifest_schema_version", "capture_state",
    "capture_committed", "capture_healthy", "full_device_span", "validity_aware",
    "automatic_eligible", "explicit_eligible", "promotion_allowed", "evidence_only",
    "profile_revision_digest", "sample_rate_hz", "pipeline_definition_id",
    "promotion_authority_digest", "reason",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  literal(item.source_type, "LIVE", `${path}.source_type`);
  literal(item.source_manifest_schema_version, 3, `${path}.source_manifest_schema_version`);
  const captureState = oneOf(item.capture_state, ["committed", "degraded"], `${path}.capture_state`);
  if (boolean(item.capture_committed, `${path}.capture_committed`) !== (captureState === "committed")) {
    fail(path, "capture state and committed flag disagree");
  }
  for (const key of [
    "capture_healthy", "full_device_span", "validity_aware", "automatic_eligible",
    "explicit_eligible", "promotion_allowed",
  ]) literal(item[key], true, `${path}.${key}`);
  literal(item.evidence_only, false, `${path}.evidence_only`);
  string(item.profile_revision_digest, `${path}.profile_revision_digest`);
  oneOf(item.sample_rate_hz, sampleRates, `${path}.sample_rate_hz`);
  string(item.pipeline_definition_id, `${path}.pipeline_definition_id`);
  string(item.promotion_authority_digest, `${path}.promotion_authority_digest`);
  const expectedReason = captureState === "committed"
    ? "Promoted reviewed V3 Standard-native capture is Current"
    : "Promoted reviewed V3 Standard-native capture is Current with partial validity coverage";
  literal(item.reason, expectedReason, `${path}.reason`);
}

function assertV3SufficientStatistics(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "receiver_path_count", "valid_complex_sample_count",
    "energy_sum_ci16_squared", "clipped_component_count", "clipped_complex_sample_count",
    "clipped_complex_fraction", "mean_power_full_scale_squared",
    "full_scale_component_magnitude", "constant_iq", "minimum_i", "maximum_i",
    "minimum_q", "maximum_q",
  ], path);
  literal(item.schema_version, 1, `${path}.schema_version`);
  for (const key of [
    "receiver_path_count", "valid_complex_sample_count", "energy_sum_ci16_squared",
    "clipped_component_count", "clipped_complex_sample_count",
  ]) nonnegativeInteger(item[key], `${path}.${key}`);
  number(item.clipped_complex_fraction, `${path}.clipped_complex_fraction`);
  number(item.mean_power_full_scale_squared, `${path}.mean_power_full_scale_squared`);
  literal(item.full_scale_component_magnitude, 32768, `${path}.full_scale_component_magnitude`);
  boolean(item.constant_iq, `${path}.constant_iq`);
  for (const key of ["minimum_i", "maximum_i", "minimum_q", "maximum_q"])
    integer(item[key], `${path}.${key}`);
}

function assertV3Opportunities(value: unknown, path: string): void {
  const item = object(value, path);
  const counters = [
    "scheduled_count", "valid_count", "analyzed_count", "candidate_count",
    "no_candidate_count", "insufficient_count", "gap_excluded_count",
    "continuity_boundary_excluded_count", "outside_span_count", "qam_complete_count",
    "qam_no_result_count", "qam_insufficient_count", "qam_not_evaluated_count",
  ];
  exactKeys(item, ["schema_version", ...counters], path);
  literal(item.schema_version, 1, `${path}.schema_version`);
  counters.forEach((key) => nonnegativeInteger(item[key], `${path}.${key}`));
  if (item.scheduled_count !== (
    Number(item.valid_count) + Number(item.gap_excluded_count)
    + Number(item.continuity_boundary_excluded_count) + Number(item.outside_span_count)
  )) fail(path, "scheduled opportunity counters do not close");
  if (item.analyzed_count !== item.valid_count || item.analyzed_count !== (
    Number(item.candidate_count) + Number(item.no_candidate_count) + Number(item.insufficient_count)
  )) fail(path, "analyzed opportunity counters do not close");
}

function assertV3Qam(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "algorithm_version", "qam_result_count", "correct_symbol_count",
    "symbol_count", "frame_count", "squared_error_sum", "reference_energy_sum",
    "hard_symbol_accuracy", "rms_evm", "known_symbols_only",
    "invalid_device_axis_samples_included",
  ], path);
  literal(item.schema_version, 1, `${path}.schema_version`);
  literal(item.algorithm_version, "known-qin-primary-qam-sufficient-statistics-v1", `${path}.algorithm_version`);
  for (const key of ["qam_result_count", "correct_symbol_count", "symbol_count", "frame_count"])
    nonnegativeInteger(item[key], `${path}.${key}`);
  string(item.squared_error_sum, `${path}.squared_error_sum`);
  string(item.reference_energy_sum, `${path}.reference_energy_sum`);
  nullableString(item.hard_symbol_accuracy, `${path}.hard_symbol_accuracy`);
  nullableString(item.rms_evm, `${path}.rms_evm`);
  literal(item.known_symbols_only, true, `${path}.known_symbols_only`);
  literal(item.invalid_device_axis_samples_included, false, `${path}.invalid_device_axis_samples_included`);
}

function assertV3Tracks(value: unknown, path: string): void {
  const item = object(value, path);
  const counters = [
    "segment_count", "analyzed_segment_count", "source_trajectory_count",
    "returned_trajectory_count", "truncated_trajectory_count",
  ];
  exactKeys(item, ["schema_version", ...counters, "cross_segment_association_permitted"], path);
  literal(item.schema_version, 1, `${path}.schema_version`);
  counters.forEach((key) => nonnegativeInteger(item[key], `${path}.${key}`));
  literal(item.cross_segment_association_permitted, false, `${path}.cross_segment_association_permitted`);
}

function assertV3Interval(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["schema_version", "start_utc_ns", "stop_utc_ns", "timing_basis"], path);
  literal(item.schema_version, 1, `${path}.schema_version`);
  const start = nonnegativeInteger(item.start_utc_ns, `${path}.start_utc_ns`);
  const stop = nonnegativeInteger(item.stop_utc_ns, `${path}.stop_utc_ns`);
  if (stop <= start) fail(path, "valid UTC interval is not positive");
  literal(item.timing_basis, "first-sample-bracket-nominal-rate-inner-v1", `${path}.timing_basis`);
}

function assertV3Terminal(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "expected_complex_sample_count", "valid_complex_sample_count",
    "missing_complex_sample_count", "coverage_fraction", "coverage_status",
    "sufficient_statistics", "terminal_opportunities", "qam_statistics", "terminal_tracks",
    "scientific_disposition", "valid_utc_intervals", "valid_samples_only",
    "stateful_resets_at_continuity_boundaries", "cross_gap_operation_permitted",
    "reducer_uses_sufficient_statistics",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  const expected = nonnegativeInteger(item.expected_complex_sample_count, `${path}.expected_complex_sample_count`);
  const valid = nonnegativeInteger(item.valid_complex_sample_count, `${path}.valid_complex_sample_count`);
  const missing = nonnegativeInteger(item.missing_complex_sample_count, `${path}.missing_complex_sample_count`);
  if (expected !== valid + missing || expected === 0 || valid === 0) fail(path, "sample counters do not close");
  const fraction = number(item.coverage_fraction, `${path}.coverage_fraction`);
  if (Math.abs(fraction - valid / expected) > 1e-12) fail(path, "coverage fraction differs from sample counters");
  const coverage = oneOf(item.coverage_status, coverageStates, `${path}.coverage_status`);
  if ((coverage === "complete" && missing !== 0)
    || (coverage === "partial_coverage" && missing === 0)) {
    fail(path, "coverage status differs from missing support");
  }
  assertV3SufficientStatistics(item.sufficient_statistics, `${path}.sufficient_statistics`);
  if (object(item.sufficient_statistics, `${path}.sufficient_statistics`).valid_complex_sample_count !== valid) {
    fail(path, "reducer support differs from valid sample count");
  }
  assertV3Opportunities(item.terminal_opportunities, `${path}.terminal_opportunities`);
  assertV3Qam(item.qam_statistics, `${path}.qam_statistics`);
  assertV3Tracks(item.terminal_tracks, `${path}.terminal_tracks`);
  oneOf(item.scientific_disposition, scienceStates, `${path}.scientific_disposition`);
  array(item.valid_utc_intervals, `${path}.valid_utc_intervals`).forEach((row, index) =>
    assertV3Interval(row, `${path}.valid_utc_intervals[${index}]`));
  literal(item.valid_samples_only, true, `${path}.valid_samples_only`);
  literal(item.stateful_resets_at_continuity_boundaries, true, `${path}.stateful_resets_at_continuity_boundaries`);
  literal(item.cross_gap_operation_permitted, false, `${path}.cross_gap_operation_permitted`);
  literal(item.reducer_uses_sufficient_statistics, true, `${path}.reducer_uses_sufficient_statistics`);
}

function assertV3Subject(value: unknown, path: string): asserts value is StandardNativeSubjectSummaryV3 {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "subject_id", "session_id", "subject_kind", "label", "derived",
    "receiver_paths", "expected_path_count", "completed_path_count", "child_subject_ids",
    "state", "ordinary_current", "coverage_status", "scientific_disposition",
    "pipeline_release", "desired_pipeline_release_id", "reuse", "eligibility", "terminal",
    "evidence_label",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  string(item.subject_id, `${path}.subject_id`);
  string(item.session_id, `${path}.session_id`);
  oneOf(item.subject_kind, ["receiver_path", "radio", "paired"], `${path}.subject_kind`);
  string(item.label, `${path}.label`);
  boolean(item.derived, `${path}.derived`);
  const paths = array(item.receiver_paths, `${path}.receiver_paths`);
  paths.forEach((row, index) => assertReceiverPath(row, `${path}.receiver_paths[${index}]`));
  if (nonnegativeInteger(item.expected_path_count, `${path}.expected_path_count`) !== paths.length
    || nonnegativeInteger(item.completed_path_count, `${path}.completed_path_count`) !== paths.length) {
    fail(path, "path counts do not match the exact inventory");
  }
  assertStringArray(item.child_subject_ids, `${path}.child_subject_ids`);
  literal(item.state, "current", `${path}.state`);
  literal(item.ordinary_current, true, `${path}.ordinary_current`);
  const coverage = oneOf(item.coverage_status, coverageStates, `${path}.coverage_status`);
  const science = oneOf(item.scientific_disposition, scienceStates, `${path}.scientific_disposition`);
  assertV3Release(item.pipeline_release, `${path}.pipeline_release`);
  string(item.desired_pipeline_release_id, `${path}.desired_pipeline_release_id`);
  assertReuse(item.reuse, `${path}.reuse`);
  assertV3Eligibility(item.eligibility, `${path}.eligibility`);
  assertV3Terminal(item.terminal, `${path}.terminal`);
  const terminal = object(item.terminal, `${path}.terminal`);
  if (terminal.coverage_status !== coverage || terminal.scientific_disposition !== science) {
    fail(path, "coverage or science differs from terminal evidence");
  }
  literal(item.evidence_label, "candidate evidence only", `${path}.evidence_label`);
}

function assertV3PathEvidence(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "receiver_path", "terminal", "declared_seconds", "valid_seconds",
    "continuity_segment_count", "continuity_boundary_count", "invalid_zero_fill_excluded",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  assertReceiverPath(item.receiver_path, `${path}.receiver_path`);
  assertV3Terminal(item.terminal, `${path}.terminal`);
  const declared = number(item.declared_seconds, `${path}.declared_seconds`);
  const valid = number(item.valid_seconds, `${path}.valid_seconds`);
  if (declared <= 0 || valid <= 0 || valid > declared) fail(path, "valid/declared seconds are invalid");
  const segments = nonnegativeInteger(item.continuity_segment_count, `${path}.continuity_segment_count`);
  const boundaries = nonnegativeInteger(item.continuity_boundary_count, `${path}.continuity_boundary_count`);
  if (segments < 1 || boundaries !== segments - 1) fail(path, "continuity segment counters do not close");
  literal(item.invalid_zero_fill_excluded, true, `${path}.invalid_zero_fill_excluded`);
}

function assertV3Trajectory(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "receiver_path_id", "continuity_segment_index", "trajectory_id",
    "start_s", "end_s", "reference_time_s", "polynomial_degree",
    "absolute_coefficients_hz", "support_count", "automatic_correction_eligible",
    "replay_tier", "cross_segment_association_permitted",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  string(item.receiver_path_id, `${path}.receiver_path_id`);
  nonnegativeInteger(item.continuity_segment_index, `${path}.continuity_segment_index`);
  string(item.trajectory_id, `${path}.trajectory_id`);
  const start = number(item.start_s, `${path}.start_s`);
  const stop = number(item.end_s, `${path}.end_s`);
  number(item.reference_time_s, `${path}.reference_time_s`);
  if (stop < start) fail(path, "trajectory extent is reversed");
  const degree = oneOf(item.polynomial_degree, [1, 2, 3], `${path}.polynomial_degree`);
  const coefficients = array(item.absolute_coefficients_hz, `${path}.absolute_coefficients_hz`);
  if (coefficients.length !== degree + 1) fail(path, "coefficient count differs from polynomial degree");
  coefficients.forEach((coefficient, index) => number(coefficient, `${path}.absolute_coefficients_hz[${index}]`));
  nonnegativeInteger(item.support_count, `${path}.support_count`);
  boolean(item.automatic_correction_eligible, `${path}.automatic_correction_eligible`);
  string(item.replay_tier, `${path}.replay_tier`);
  literal(item.cross_segment_association_permitted, false, `${path}.cross_segment_association_permitted`);
}

function assertV3ViewDescriptor(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "view_kind", "state", "href", "source_point_count",
    "png_available", "png_href", "reason",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  oneOf(item.view_kind, viewKinds, `${path}.view_kind`);
  const state = oneOf(item.state, ["available", "partial", "unavailable"], `${path}.state`);
  const href = string(item.href, `${path}.href`);
  if (!href.startsWith("/api/v2/")) fail(path, "view href is outside the Standard API");
  const count = nonnegativeInteger(item.source_point_count, `${path}.source_point_count`);
  const available = boolean(item.png_available, `${path}.png_available`);
  const pngHref = nullableString(item.png_href, `${path}.png_href`);
  if (available !== (pngHref !== null)) fail(path, "PNG availability differs from its href");
  if (pngHref !== null && !pngHref.startsWith("/api/v2/")) {
    fail(path, "PNG href is outside the Standard API");
  }
  if (state === "unavailable" && count !== 0) fail(path, "unavailable view claims source evidence");
  string(item.reason, `${path}.reason`);
}

function assertV3Detail(value: unknown): asserts value is StandardNativeSubjectDetailV3 {
  const item = object(value, "subject detail V3");
  exactKeys(item, [
    "schema_version", "subject", "time_domain", "receiver_path_expansions",
    "receiver_path_evidence", "stage_source_count", "stages", "stages_truncated",
    "trajectory_source_count", "trajectories", "trajectories_truncated", "views",
    "available_artifacts", "limitations",
  ], "subject detail V3");
  literal(item.schema_version, 3, "subject detail V3.schema_version");
  assertV3Subject(item.subject, "subject detail V3.subject");
  assertTimeDomain(item.time_domain, "subject detail V3.time_domain");
  array(item.receiver_path_expansions, "subject detail V3.receiver_path_expansions")
    .forEach((row, index) => assertV3Subject(row, `subject detail V3.receiver_path_expansions[${index}]`));
  array(item.receiver_path_evidence, "subject detail V3.receiver_path_evidence")
    .forEach((row, index) => assertV3PathEvidence(row, `subject detail V3.receiver_path_evidence[${index}]`));
  const stageCount = nonnegativeInteger(item.stage_source_count, "subject detail V3.stage_source_count");
  const stages = array(item.stages, "subject detail V3.stages");
  stages.forEach((row, index) => assertStage(row, `subject detail V3.stages[${index}]`));
  const stagesTruncated = boolean(item.stages_truncated, "subject detail V3.stages_truncated");
  if (stageCount < stages.length || stagesTruncated !== (stageCount > stages.length)) fail("subject detail V3", "stage bounds do not close");
  const trajectoryCount = nonnegativeInteger(item.trajectory_source_count, "subject detail V3.trajectory_source_count");
  const trajectories = array(item.trajectories, "subject detail V3.trajectories");
  trajectories.forEach((row, index) => assertV3Trajectory(row, `subject detail V3.trajectories[${index}]`));
  const trajectoriesTruncated = boolean(item.trajectories_truncated, "subject detail V3.trajectories_truncated");
  if (trajectoryCount < trajectories.length || trajectoriesTruncated !== (trajectoryCount > trajectories.length)) fail("subject detail V3", "trajectory bounds do not close");
  const views = array(item.views, "subject detail V3.views");
  views.forEach((row, index) => assertV3ViewDescriptor(row, `subject detail V3.views[${index}]`));
  const kinds = views.map((row) => object(row, "subject detail V3 view").view_kind);
  if (kinds.length !== viewKinds.length || !viewKinds.every((kind) => kinds.includes(kind))) {
    fail("subject detail V3", "view inventory is not the exact six Standard views");
  }
  const artifacts = array(item.available_artifacts, "subject detail V3.available_artifacts");
  artifacts.forEach((name, index) =>
    oneOf(name, ["waterfall", "cfo-alternate"], `subject detail V3.available_artifacts[${index}]`));
  if (new Set(artifacts).size !== artifacts.length) fail("subject detail V3", "artifact inventory is duplicated");
  const waterfallPng = views.some((view) => {
    const row = object(view, "subject detail V3 view");
    return row.view_kind === "waterfall" && row.png_available === true;
  });
  if (artifacts.includes("waterfall") !== waterfallPng) {
    fail("subject detail V3", "waterfall artifact inventory differs from its PNG descriptor");
  }
  assertStringArray(item.limitations, "subject detail V3.limitations");
}

function assertV3ProductRef(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "product_id", "scope_key", "kind", "product_schema_version", "digest",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  nonnegativeInteger(item.product_id, `${path}.product_id`);
  string(item.scope_key, `${path}.scope_key`);
  string(item.kind, `${path}.kind`);
  nonnegativeInteger(item.product_schema_version, `${path}.product_schema_version`);
  string(item.digest, `${path}.digest`);
}

function assertV3SourceProof(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, ["schema_version", "run_manifest_digest", "products", "content_digest"], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  string(item.run_manifest_digest, `${path}.run_manifest_digest`);
  array(item.products, `${path}.products`).forEach((row, index) =>
    assertV3ProductRef(row, `${path}.products[${index}]`));
  string(item.content_digest, `${path}.content_digest`);
}

function assertV3MetricSeries(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "series_id", "receiver_path_id", "label", "unit",
    "source_point_count", "points", "truncated",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  string(item.series_id, `${path}.series_id`);
  string(item.receiver_path_id, `${path}.receiver_path_id`);
  string(item.label, `${path}.label`);
  oneOf(item.unit, ["dBFS", "fraction", "response", "accuracy", "EVM"], `${path}.unit`);
  const source = nonnegativeInteger(item.source_point_count, `${path}.source_point_count`);
  const points = array(item.points, `${path}.points`);
  points.forEach((point, index) => {
    const rowPath = `${path}.points[${index}]`;
    const row = object(point, rowPath);
    exactKeys(row, ["schema_version", "time_s", "value", "valid"], rowPath);
    literal(row.schema_version, 3, `${rowPath}.schema_version`);
    number(row.time_s, `${rowPath}.time_s`);
    const valid = boolean(row.valid, `${rowPath}.valid`);
    if (row.value !== null) number(row.value, `${rowPath}.value`);
    if (valid !== (row.value !== null)) fail(rowPath, "validity differs from nullable value");
  });
  const truncated = boolean(item.truncated, `${path}.truncated`);
  if (source < points.length || truncated !== (source > points.length)) fail(path, "series bounds do not close");
}

function assertV3WaterfallTile(value: unknown, path: string): void {
  const item = object(value, path);
  exactKeys(item, [
    "schema_version", "receiver_path_id", "time_bin", "time_start_s", "time_stop_s",
    "sample_start", "sample_stop", "transform_count", "valid", "power_dbfs",
  ], path);
  literal(item.schema_version, 3, `${path}.schema_version`);
  string(item.receiver_path_id, `${path}.receiver_path_id`);
  nonnegativeInteger(item.time_bin, `${path}.time_bin`);
  const timeStart = number(item.time_start_s, `${path}.time_start_s`);
  const timeStop = number(item.time_stop_s, `${path}.time_stop_s`);
  const sampleStart = nonnegativeInteger(item.sample_start, `${path}.sample_start`);
  const sampleStop = nonnegativeInteger(item.sample_stop, `${path}.sample_stop`);
  if (timeStop <= timeStart || sampleStop <= sampleStart) fail(path, "tile extent is not positive");
  const transforms = nonnegativeInteger(item.transform_count, `${path}.transform_count`);
  const valid = boolean(item.valid, `${path}.valid`);
  if (valid !== (transforms > 0)) fail(path, "validity differs from transform support");
  const powers = array(item.power_dbfs, `${path}.power_dbfs`);
  if (powers.length === 0) fail(path, "frequency-bin payload is empty");
  powers.forEach((power, index) => {
    if (valid) number(power, `${path}.power_dbfs[${index}]`);
    else if (power !== null) fail(path, "missing waterfall power must be null, never zero-filled measurement");
  });
}

function assertV2Plot(value: unknown): asserts value is StandardPlotViewV2 {
  const item = object(value, "plot view V2");
  literal(item.schema_version, 2, "plot view V2.schema_version");
  string(item.session_id, "plot view V2.session_id");
  string(item.subject_id, "plot view V2.subject_id");
  oneOf(item.view_kind, viewKinds, "plot view V2.view_kind");
  oneOf(item.state, ["available", "partial", "unavailable"], "plot view V2.state");
  assertTimeDomain(item.time_domain, "plot view V2.time_domain");
  assertStringArray(item.receiver_path_ids, "plot view V2.receiver_path_ids");
  array(item.series, "plot view V2.series");
  array(item.waterfall_cells, "plot view V2.waterfall_cells");
  array(item.cfo_observations, "plot view V2.cfo_observations");
  array(item.trajectory_curves, "plot view V2.trajectory_curves");
}

function assertV3Plot(value: unknown): asserts value is StandardNativePlotViewV3 {
  const item = object(value, "plot view V3");
  exactKeys(item, [
    "schema_version", "session_id", "subject_id", "view_kind", "state", "time_domain",
    "receiver_path_ids", "sample_rate_hz", "source_proof", "source_point_count",
    "returned_point_count", "truncated", "metric_series", "frequency_bin_centers_hz",
    "waterfall_tiles", "trajectories", "reason", "projection_digest",
  ], "plot view V3");
  literal(item.schema_version, 3, "plot view V3.schema_version");
  string(item.session_id, "plot view V3.session_id");
  string(item.subject_id, "plot view V3.subject_id");
  const viewKind = oneOf(item.view_kind, viewKinds, "plot view V3.view_kind");
  const state = oneOf(item.state, ["available", "partial", "unavailable"], "plot view V3.state");
  assertTimeDomain(item.time_domain, "plot view V3.time_domain");
  assertStringArray(item.receiver_path_ids, "plot view V3.receiver_path_ids");
  oneOf(item.sample_rate_hz, sampleRates, "plot view V3.sample_rate_hz");
  assertV3SourceProof(item.source_proof, "plot view V3.source_proof");
  const source = nonnegativeInteger(item.source_point_count, "plot view V3.source_point_count");
  const returned = nonnegativeInteger(item.returned_point_count, "plot view V3.returned_point_count");
  const truncated = boolean(item.truncated, "plot view V3.truncated");
  const series = array(item.metric_series, "plot view V3.metric_series");
  series.forEach((row, index) => assertV3MetricSeries(row, `plot view V3.metric_series[${index}]`));
  const frequencies = array(item.frequency_bin_centers_hz, "plot view V3.frequency_bin_centers_hz");
  frequencies.forEach((frequency, index) => number(frequency, `plot view V3.frequency_bin_centers_hz[${index}]`));
  const tiles = array(item.waterfall_tiles, "plot view V3.waterfall_tiles");
  tiles.forEach((row, index) => {
    assertV3WaterfallTile(row, `plot view V3.waterfall_tiles[${index}]`);
    if (array(object(row, "plot view V3 waterfall tile").power_dbfs, "plot view V3 waterfall power").length !== frequencies.length) {
      fail(`plot view V3.waterfall_tiles[${index}]`, "tile width differs from frequency axis");
    }
  });
  const trajectories = array(item.trajectories, "plot view V3.trajectories");
  trajectories.forEach((row, index) => assertV3Trajectory(row, `plot view V3.trajectories[${index}]`));
  const calculatedReturned = series.reduce<number>((count, row) =>
    count + array(object(row, "plot view V3 metric series").points, "plot view V3 metric points").length, 0)
    + tiles.length + trajectories.length;
  if (returned !== calculatedReturned || source < returned || truncated !== (source > returned)) {
    fail("plot view V3", "source and returned point counts do not close");
  }
  if (state === "unavailable" && returned !== 0) fail("plot view V3", "unavailable view carries evidence");
  if (viewKind === "waterfall") {
    if (series.length || trajectories.length || frequencies.length === 0) fail("plot view V3", "waterfall payload shape is invalid");
  } else if (viewKind === "cfo_trajectory") {
    if (series.length || tiles.length || frequencies.length) fail("plot view V3", "trajectory payload shape is invalid");
  } else if (tiles.length || trajectories.length || frequencies.length) {
    fail("plot view V3", "metric payload shape is invalid");
  }
  string(item.reason, "plot view V3.reason");
  string(item.projection_digest, "plot view V3.projection_digest");
}

export function parseStandardSubjectHierarchy(value: unknown): StandardSubjectHierarchy {
  const item = object(value, "subject hierarchy");
  if (item.schema_version === 2) {
    string(item.session_id, "subject hierarchy V2.session_id");
    oneOf(item.source_type, ["LIVE", "IMPORT", "TEST"], "subject hierarchy V2.source_type");
    assertV2Eligibility(item.eligibility, "subject hierarchy V2.eligibility");
    string(item.generated_at, "subject hierarchy V2.generated_at");
    array(item.rows, "subject hierarchy V2.rows").forEach((row, index) =>
      assertV2Subject(row, `subject hierarchy V2.rows[${index}]`));
    return item as unknown as StandardSubjectHierarchyV2;
  }
  if (item.schema_version === 3) {
    exactKeys(item, ["schema_version", "session_id", "source_type", "eligibility", "generated_at", "rows"], "subject hierarchy V3");
    literal(item.schema_version, 3, "subject hierarchy V3.schema_version");
    string(item.session_id, "subject hierarchy V3.session_id");
    literal(item.source_type, "LIVE", "subject hierarchy V3.source_type");
    assertV3Eligibility(item.eligibility, "subject hierarchy V3.eligibility");
    string(item.generated_at, "subject hierarchy V3.generated_at");
    array(item.rows, "subject hierarchy V3.rows").forEach((row, index) =>
      assertV3Subject(row, `subject hierarchy V3.rows[${index}]`));
    return item as unknown as StandardNativeSubjectHierarchyV3;
  }
  fail("subject hierarchy", "unsupported schema_version; expected 2 or 3");
}

export function parseStandardSubjectDetail(value: unknown): StandardSubjectDetail {
  const item = object(value, "subject detail");
  if (item.schema_version === 2) {
    assertV2Detail(item);
    return item;
  }
  if (item.schema_version === 3) {
    assertV3Detail(item);
    return item;
  }
  fail("subject detail", "unsupported schema_version; expected 2 or 3");
}

export function parseStandardPlotView(value: unknown): StandardPlotView {
  const item = object(value, "plot view");
  if (item.schema_version === 2) {
    assertV2Plot(item);
    return item;
  }
  if (item.schema_version === 3) {
    assertV3Plot(item);
    return item;
  }
  fail("plot view", "unsupported schema_version; expected 2 or 3");
}

export function assertMatchingStandardMajor(
  hierarchy: StandardSubjectHierarchy,
  detail: StandardSubjectDetail,
): void {
  if (hierarchy.schema_version !== detail.schema_version) {
    fail("presentation", "hierarchy and detail schema versions differ");
  }
}
