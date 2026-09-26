export interface AdaptiveCoverage {
  target_index: number;
  target: { channel: number; edge: "lower" | "upper"; rf_center_hz: number; if_center_hz: number };
  retained_visits: number;
  valid_seconds: number;
  allocation_ppm: number | null;
  maximum_revisit_seconds: number | null;
  maximum_unobserved_seconds: number | null;
}

export interface LegacyAdaptiveCapture {
  schema_version: 1; kind: "adaptive_hop_history_item";
  session_id: string; input_manifest_sha256: string; radio_id: string;
  mode: "shadow" | "adaptive"; policy_generation: string;
  recorded_at: string; finalized_at: string; captured_at: string | null;
  utc_qualified: boolean; utc_bracket_width_ms: number | null;
  nominal_duration_seconds: 300; valid_visit_ms: 120;
  sample_rate_hz: 2500000 | 5000000; bandwidth_hz: 2500000 | 5000000;
  started_visits: number; retained_visits: number;
  source_span_attested: boolean; source_span_seconds: number | null;
  valid_duty_ppm: number | null; capture_qualified: boolean;
  terminal_state: "completed" | "cancelled"; restoration_status: "restored";
  fallback_choices: number; target_coverage: AdaptiveCoverage[];
  analysis_state: "not_integrated";
}

export interface HostFeedbackSummary {
  schema_version: 1; complete_visits: number; healthy: number; degraded: number;
  unknown_feedback: number; accepted: number; source_ended: number; rejected: number; not_submitted: number;
  maximum_host_result_age_ms: number | null; maximum_feedback_call_ms: number | null;
  first_feedback_error: string | null;
}
export interface HostAdaptiveCaptureV2 extends Omit<LegacyAdaptiveCapture, "schema_version" | "sample_rate_hz" | "bandwidth_hz" | "analysis_state"> {
  schema_version: 2; sample_rate_hz: 10000000; bandwidth_hz: 10000000; analysis_state: "separate_product";
  radio_serial: string; physical_receiver: 0 | 1;
  decision_configuration: { schema_version: 1; execution: "host"; decision_rate_hz: 2500000;
    source_rate_hz: 10000000; decimation_factor: 4; filter_taps: 161; screen_count: 6;
    maximum_confirmations: 1; detector_manifest_sha256: string };
  host_feedback: HostFeedbackSummary;
}
export interface HostAdaptiveCaptureV3 extends Omit<HostAdaptiveCaptureV2, "schema_version" | "sample_rate_hz" | "bandwidth_hz" | "physical_receiver" | "decision_configuration"> {
  schema_version: 3; sample_rate_hz: 15000000 | 20000000; bandwidth_hz: 15000000 | 20000000;
  physical_receiver: 0;
  decision_configuration: { schema_version: 2; execution: "host"; decision_rate_hz: 2500000;
    source_rate_hz: 15000000 | 20000000; decimation_factor: 6 | 8; filter_taps: 201 | 257;
    screen_count: 6; maximum_confirmations: 1; detector_manifest_sha256: string };
}
export interface EdgeAdaptiveCaptureV4 extends Omit<LegacyAdaptiveCapture, "schema_version" | "sample_rate_hz" | "bandwidth_hz" | "analysis_state"> {
  schema_version: 4; sample_rate_hz: 2500000; bandwidth_hz: 2500000; analysis_state: "separate_product";
  radio_serial: string; selected_edge: "lower" | "upper"; allowed_target_mask: 15 | 240;
}
export type HostAdaptiveCapture = HostAdaptiveCaptureV2 | HostAdaptiveCaptureV3;
export interface DualRx10mCaptureV5 extends Omit<EdgeAdaptiveCaptureV4, "schema_version" | "sample_rate_hz" | "bandwidth_hz"> {
  schema_version: 5; sample_rate_hz: 10000000; bandwidth_hz: 10000000;
}
export interface Feature103CaptureV6 extends Omit<EdgeAdaptiveCaptureV4, "schema_version" | "sample_rate_hz" | "bandwidth_hz"> {
  schema_version: 6; sample_rate_hz: 2500000 | 5000000 | 10000000; bandwidth_hz: 2500000 | 5000000 | 10000000;
}
export interface Feature104CaptureV7 extends Omit<EdgeAdaptiveCaptureV4, "schema_version" | "sample_rate_hz" | "bandwidth_hz"> {
  schema_version: 7; sample_rate_hz: 2500000 | 10000000 | 15000000; bandwidth_hz: 2500000 | 10000000 | 15000000;
}
export interface VariableDwellCaptureV8 extends Omit<EdgeAdaptiveCaptureV4, "schema_version" | "nominal_duration_seconds" | "sample_rate_hz" | "bandwidth_hz"> {
  schema_version: 8; nominal_duration_seconds: number;
  sample_rate_hz: 2500000 | 10000000; bandwidth_hz: 2500000 | 10000000;
  active_dwell_ms: 120 | 240 | 360;
  recorded_gain_mode: "manual" | "slow_attack" | null;
  recorded_manual_gain_db: number | null;
}
export interface FourRateVariableDwellCaptureV9 extends Omit<VariableDwellCaptureV8, "schema_version" | "sample_rate_hz" | "bandwidth_hz"> {
  schema_version: 9;
  sample_rate_hz: 2500000 | 5000000 | 7500000 | 10000000;
  bandwidth_hz: 2500000 | 5000000 | 7500000 | 10000000;
}
export type AdaptiveCapture = LegacyAdaptiveCapture | HostAdaptiveCapture | EdgeAdaptiveCaptureV4 | DualRx10mCaptureV5 | Feature103CaptureV6 | Feature104CaptureV7 | VariableDwellCaptureV8 | FourRateVariableDwellCaptureV9;
export interface HostDecisionNumericsV1 {
  schema_version: 1; outcome: "unknown" | "detected" | "not_detected";
  screen_mask: 63; confirmation_mask: number; screen_scores: number[];
  supported_start: 40; supported_end: 300000; candidate_supported: boolean; fractional_complete: boolean;
}
export interface HostDecisionNumericsV2 extends Omit<HostDecisionNumericsV1, "schema_version" | "supported_start"> {
  schema_version: 2; source_rate_hz: 15000000 | 20000000; supported_start: 34 | 32;
}
interface HostDecisionViewBase {
  visit_index: number;
  health: "healthy" | "queue_overflow" | "detector_failure" | "expired";
  failure: string | null; feedback_error: string | null;
  feedback_outcome: "unknown" | "detected" | "not_detected";
  feedback_disposition: "accepted" | "source_ended" | "rejected" | "not_submitted";
  host_result_age_ms: number; worker_elapsed_ms: number | null; feedback_call_ms: number | null;
}
export interface HostDecisionViewV1 extends HostDecisionViewBase { schema_version: 1; numerics: HostDecisionNumericsV1 | null; }
export interface HostDecisionViewV2 extends HostDecisionViewBase { schema_version: 2; numerics: HostDecisionNumericsV2 | null; }
export type HostDecisionView = HostDecisionViewV1 | HostDecisionViewV2;

export interface AdaptiveVisit {
  visit_index: number; target_index: number; retained: boolean;
  invalid_start_seconds: number; valid_start_seconds: number; valid_end_seconds: number | null;
  valid_start_counter: string; valid_end_counter: string | null; decision_counter: string;
  basis_visit: number | null; proposed_target_index: number;
  reason: "warmup" | "weighted" | "exploration" | "none_active" | "fault_fallback";
  active_mask: number; quiet_mask: number; consecutive_misses: number;
  cooldown_remaining_seconds: number;
}

export interface AdaptivePage {
  schema_version: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8; kind: "adaptive_hop_history_page";
  cursor: number; limit: number; total: number; next_cursor: number | null;
  items: AdaptiveCapture[];
}

export interface AdaptiveDetail {
  schema_version: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9; kind: "adaptive_hop_session_detail";
  capture: AdaptiveCapture; source_origin_counter: string | null; visits: AdaptiveVisit[];
  host_decisions?: HostDecisionView[];
}

function counter(value: unknown): value is string {
  return typeof value === "string" && /^(0|[1-9][0-9]{0,19})$/.test(value)
    && BigInt(value) <= 18446744073709551615n;
}
function integer(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}
function seconds(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}
function optionalSeconds(value: unknown): boolean { return value === null || seconds(value); }
function variableCoverageSecondsArePossible(row: AdaptiveCoverage, activeDwellMs: number): boolean {
  const baseMs = row.retained_visits * 120;
  const stepMs = activeDwellMs - 120;
  const validMs = row.valid_seconds * 1000;
  if (stepMs === 0) return Math.abs(validMs - baseMs) <= 1e-9;
  const activeVisits = Math.round((validMs - baseMs) / stepMs);
  return activeVisits >= 0 && activeVisits <= row.retained_visits
    && Math.abs(validMs - (baseMs + activeVisits * stepMs)) <= 1e-9;
}
function isVariableDwell(c: AdaptiveCapture): c is VariableDwellCaptureV8 | FourRateVariableDwellCaptureV9 {
  return c.schema_version === 8 || c.schema_version === 9;
}

function validateCapture(c: AdaptiveCapture): void {
  const variableDwell = Boolean(c) && isVariableDwell(c);
  if (!c || c.kind !== "adaptive_hop_history_item" || ![1, 2, 3, 4, 5, 6, 7, 8, 9].includes(c.schema_version)
      || typeof c.session_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(c.session_id)
      || !/^sha256:[0-9a-f]{64}$/.test(c.input_manifest_sha256) || !counter(c.policy_generation)
      || !["adaptive", "shadow"].includes(c.mode) || typeof c.radio_id !== "string"
      || ![c.recorded_at, c.finalized_at].every(v => typeof v === "string" && Number.isFinite(Date.parse(v)))
      || (c.captured_at !== null && (typeof c.captured_at !== "string" || !Number.isFinite(Date.parse(c.captured_at))))
      || (variableDwell ? !integer(c.nominal_duration_seconds, 300) || c.nominal_duration_seconds < 1 : c.nominal_duration_seconds !== 300) || c.valid_visit_ms !== 120
      || !(c.schema_version === 9 ? [2500000, 5000000, 7500000, 10000000].includes(c.sample_rate_hz) : c.schema_version === 8 ? [2500000, 10000000].includes(c.sample_rate_hz) : c.schema_version === 7 ? [2500000, 10000000, 15000000].includes(c.sample_rate_hz) : c.schema_version === 6 ? [2500000, 5000000, 10000000].includes(c.sample_rate_hz) : c.schema_version === 5 ? c.sample_rate_hz === 10000000 : c.schema_version === 3 ? [15000000, 20000000].includes(c.sample_rate_hz) : c.schema_version === 2 ? c.sample_rate_hz === 10000000 : c.schema_version === 4 ? c.sample_rate_hz === 2500000 : [2500000, 5000000].includes(c.sample_rate_hz)) || c.bandwidth_hz !== c.sample_rate_hz
      || !integer(c.started_visits, 2500) || !integer(c.retained_visits, c.started_visits)
      || !integer(c.fallback_choices, c.started_visits)
      || !optionalSeconds(c.source_span_seconds) || !optionalSeconds(c.utc_bracket_width_ms)
      || (c.valid_duty_ppm !== null && !integer(c.valid_duty_ppm, 1000000))
      || typeof c.source_span_attested !== "boolean" || typeof c.utc_qualified !== "boolean"
      || typeof c.capture_qualified !== "boolean"
      || c.source_span_attested !== (c.source_span_seconds !== null)
      || c.source_span_attested !== (c.valid_duty_ppm !== null)
      || (c.utc_qualified && c.captured_at === null)
      || !["completed", "cancelled"].includes(c.terminal_state) || c.restoration_status !== "restored"
      || c.analysis_state !== (c.schema_version !== 1 ? "separate_product" : "not_integrated") || !Array.isArray(c.target_coverage) || c.target_coverage.length !== 8) {
    throw new Error("Adaptive capture evidence is invalid");
  }
  if (c.schema_version === 4 || c.schema_version === 5 || c.schema_version === 6 || c.schema_version === 7 || c.schema_version === 8 || c.schema_version === 9) {
    const expectedMask = c.selected_edge === "lower" ? 15 : c.selected_edge === "upper" ? 240 : 0;
    const excluded = c.selected_edge === "lower" ? c.target_coverage.slice(4) : c.target_coverage.slice(0, 4);
    if (!c.radio_serial || c.allowed_target_mask !== expectedMask || excluded.some(row => row.retained_visits !== 0)) {
      throw new Error("One-edge adaptive policy evidence is invalid");
    }
    if ((c.schema_version === 8 || c.schema_version === 9) && (![120, 240, 360].includes(c.active_dwell_ms)
        || ![null, "manual", "slow_attack"].includes(c.recorded_gain_mode)
        || (c.recorded_gain_mode === "manual") !== (typeof c.recorded_manual_gain_db === "number" && Number.isFinite(c.recorded_manual_gain_db)))) {
      throw new Error("Adaptive recorded gain evidence is invalid");
    }
  } else if (c.schema_version !== 1) {
    const d = c.decision_configuration, h = c.host_feedback;
    if (![0, 1].includes(c.physical_receiver) || typeof c.radio_serial !== "string" || !c.radio_serial
        || !d || d.schema_version !== c.schema_version - 1 || d.execution !== "host" || d.source_rate_hz !== c.sample_rate_hz
        || d.decision_rate_hz !== 2500000
        || !(c.schema_version === 2 ? d.decimation_factor === 4 && d.filter_taps === 161
          : c.physical_receiver === 0 && ((c.sample_rate_hz === 15000000 && d.decimation_factor === 6 && d.filter_taps === 201)
            || (c.sample_rate_hz === 20000000 && d.decimation_factor === 8 && d.filter_taps === 257)))
        || d.screen_count !== 6 || d.maximum_confirmations !== 1 || !/^sha256:[0-9a-f]{64}$/.test(d.detector_manifest_sha256)
        || !h || h.schema_version !== 1 || h.complete_visits !== c.retained_visits
        || ![h.healthy, h.degraded, h.unknown_feedback, h.accepted, h.source_ended, h.rejected, h.not_submitted].every(v => integer(v, c.retained_visits))
        || h.healthy + h.degraded !== c.retained_visits
        || h.accepted + h.source_ended + h.rejected + h.not_submitted !== c.retained_visits
        || !optionalSeconds(h.maximum_host_result_age_ms) || !optionalSeconds(h.maximum_feedback_call_ms)
        || (h.first_feedback_error !== null && typeof h.first_feedback_error !== "string")) {
      throw new Error("Native adaptive host feedback is invalid");
    }
  }
  c.target_coverage.forEach((row, i) => {
    if (!row || row.target_index !== i || !row.target || row.target.channel !== i % 4 + 1
        || row.target.edge !== (i < 4 ? "lower" : "upper")
        || !seconds(row.target.rf_center_hz) || !seconds(row.target.if_center_hz)
        || !integer(row.retained_visits, c.retained_visits) || !seconds(row.valid_seconds)
        || (variableDwell
          && !variableCoverageSecondsArePossible(row, c.active_dwell_ms))
        || (row.allocation_ppm !== null && !integer(row.allocation_ppm, 1000000))
        || !optionalSeconds(row.maximum_revisit_seconds) || !optionalSeconds(row.maximum_unobserved_seconds)) {
      throw new Error("Adaptive coverage evidence is invalid");
    }
  });
  if (c.target_coverage.reduce((sum, row) => sum + row.retained_visits, 0) !== c.retained_visits) {
    throw new Error("Adaptive coverage inventory differs");
  }
}

export const ADAPTIVE_SESSION_PAGE_SIZE = 10;

export async function getAdaptiveSessions(cursor: number, signal?: AbortSignal): Promise<AdaptivePage | null> {
  const query = `cursor=${cursor}&limit=${ADAPTIVE_SESSION_PAGE_SIZE}`;
  let response = await fetch(`/api/v3/scanner/adaptive-sessions?${query}`, { signal });
  if (response.status === 404) response = await fetch(`/api/v2/scanner/adaptive-sessions?${query}`, { signal });
  if (response.status === 404) response = await fetch(`/api/v1/scanner/adaptive-sessions?${query}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Adaptive history request failed (${response.status})`);
  const page = await response.json() as AdaptivePage;
  if (!page || ![1, 2, 3, 4, 5, 6, 7, 8].includes(page.schema_version) || page.kind !== "adaptive_hop_history_page"
      || page.cursor !== cursor || page.limit !== ADAPTIVE_SESSION_PAGE_SIZE || !integer(page.total)
      || !Array.isArray(page.items) || page.items.length > page.limit
      || (page.next_cursor !== null && page.next_cursor !== cursor + page.limit)) {
    throw new Error("Adaptive history response is invalid");
  }
  page.items.forEach(validateCapture);
  return page;
}

export async function getAdaptiveSession(sessionId: string, signal?: AbortSignal): Promise<AdaptiveDetail> {
  let response = await fetch(`/api/v3/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}`, { signal });
  if (response.status === 404) response = await fetch(`/api/v2/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}`, { signal });
  if (response.status === 404) response = await fetch(`/api/v1/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}`, { signal });
  if (!response.ok) throw new Error(`Adaptive detail request failed (${response.status})`);
  const detail = await response.json() as AdaptiveDetail;
  if (!detail || ![1, 2, 3, 4, 5, 6, 7, 8, 9].includes(detail.schema_version) || detail.kind !== "adaptive_hop_session_detail") {
    throw new Error("Adaptive detail response is invalid");
  }
  validateCapture(detail.capture);
  const c = detail.capture;
  if (detail.schema_version !== c.schema_version) throw new Error("Adaptive detail major differs from capture");
  if (c.session_id !== sessionId || !Array.isArray(detail.visits) || detail.visits.length !== c.started_visits
      || (c.source_span_attested ? !counter(detail.source_origin_counter) : detail.source_origin_counter !== null)) {
    throw new Error("Adaptive detail source binding is invalid");
  }
  // Host-wide V3, feature-104 V7, and variable-dwell V8/V9 receipts explicitly
  // preserve sparse retained-visit indices. Other published majors retain a strict prefix.
  const sparse = c.schema_version === 3 || c.schema_version === 7 || c.schema_version === 8 || c.schema_version === 9;
  const retainedIndices = detail.visits.filter(v => v?.retained === true).map(v => v.visit_index);
  if (retainedIndices.length !== c.retained_visits) throw new Error("Adaptive retained visit inventory differs");
  if (c.schema_version === 2 || c.schema_version === 3) {
    if (!Array.isArray(detail.host_decisions) || detail.host_decisions.length !== c.retained_visits) throw new Error("Host decision inventory is incomplete");
    detail.host_decisions.forEach((d, i) => {
      const wide = c.schema_version === 3;
      const expectedStart = wide ? (c.sample_rate_hz === 15000000 ? 34 : 32) : 40;
      if (!d || d.schema_version !== (wide ? 2 : 1) || d.visit_index !== (wide ? retainedIndices[i] : i)
          || !["healthy", "queue_overflow", "detector_failure", "expired"].includes(d.health)
          || !["unknown", "detected", "not_detected"].includes(d.feedback_outcome)
          || !["accepted", "source_ended", "rejected", "not_submitted"].includes(d.feedback_disposition)
          || !seconds(d.host_result_age_ms) || !optionalSeconds(d.worker_elapsed_ms) || !optionalSeconds(d.feedback_call_ms)
          || (d.failure !== null && (typeof d.failure !== "string" || !d.failure))
          || (d.feedback_error !== null && (typeof d.feedback_error !== "string" || !d.feedback_error))
          || (d.feedback_error !== null) !== ["rejected", "not_submitted"].includes(d.feedback_disposition)
          || (d.feedback_call_ms === null) !== (d.feedback_disposition === "not_submitted")
          || (d.worker_elapsed_ms === null) !== (d.health === "queue_overflow")
          || (d.numerics !== null && (d.numerics.schema_version !== (wide ? 2 : 1) || d.numerics.screen_mask !== 63
            || ![1, 2, 4, 8, 16, 32].includes(d.numerics.confirmation_mask)
            || d.numerics.supported_start !== expectedStart || d.numerics.supported_end !== 300000
            || (wide && (d.numerics.schema_version !== 2 || d.numerics.source_rate_hz !== c.sample_rate_hz))
            || !["unknown", "detected", "not_detected"].includes(d.numerics.outcome)
            || typeof d.numerics.candidate_supported !== "boolean" || typeof d.numerics.fractional_complete !== "boolean"
            || !Array.isArray(d.numerics.screen_scores) || d.numerics.screen_scores.length !== 6
            || !d.numerics.screen_scores.every(v => typeof v === "number" && Number.isFinite(v))))
          || (d.health === "healthy" ? d.numerics === null || d.failure !== null || d.feedback_outcome !== d.numerics.outcome || d.host_result_age_ms > 1000
            : d.feedback_outcome !== "unknown" || d.failure === null)
          || (["queue_overflow", "detector_failure"].includes(d.health) && d.numerics !== null)) throw new Error("Host decision evidence is invalid");
    });
  }
  detail.visits.forEach((v, i) => {
    if (!v || v.visit_index !== i || !integer(v.target_index, 7) || !integer(v.proposed_target_index, 7)
        || typeof v.retained !== "boolean" || (!sparse && v.retained !== (i < c.retained_visits))
        || !counter(v.valid_start_counter) || !counter(v.decision_counter)
        || (v.retained ? !counter(v.valid_end_counter) : v.valid_end_counter !== null)
        || !seconds(v.invalid_start_seconds) || !seconds(v.valid_start_seconds)
        || (v.retained ? !seconds(v.valid_end_seconds) || v.valid_end_seconds <= v.valid_start_seconds : v.valid_end_seconds !== null)
        || (v.basis_visit !== null && !integer(v.basis_visit, i - 1))
        || !integer(v.active_mask, 255) || !integer(v.quiet_mask, 255) || (v.active_mask & v.quiet_mask) !== 0
        || !integer(v.consecutive_misses, 3) || !seconds(v.cooldown_remaining_seconds)
        || !["warmup", "weighted", "exploration", "none_active", "fault_fallback"].includes(v.reason)
        || (c.mode === "adaptive" && v.target_index !== v.proposed_target_index)
        || ((c.schema_version === 4 || c.schema_version === 5 || c.schema_version === 6 || c.schema_version === 7 || c.schema_version === 8 || c.schema_version === 9) && ((c.allowed_target_mask & (1 << v.target_index)) === 0
          || (c.allowed_target_mask & (1 << v.proposed_target_index)) === 0
          || ((v.active_mask | v.quiet_mask) & ~c.allowed_target_mask) !== 0))
        || (c.mode === "shadow" && v.target_index !== i % 8)) {
      throw new Error("Adaptive visit evidence is invalid");
    }
    const relative = Number(BigInt(v.valid_start_counter) - BigInt(detail.source_origin_counter!)) / c.sample_rate_hz;
    const retainedSamples = v.retained
      ? BigInt(v.valid_end_counter!) - BigInt(v.valid_start_counter)
      : 0n;
    const allowedSamples = c.schema_version === 8 || c.schema_version === 9
      ? [120, c.active_dwell_ms].map(ms => BigInt(c.sample_rate_hz * ms / 1000))
      : [BigInt(c.sample_rate_hz * 0.12)];
    if (relative !== v.valid_start_seconds || v.invalid_start_seconds > relative
        || BigInt(v.decision_counter) > BigInt(v.valid_start_counter)
        || (v.retained && (!allowedSamples.includes(retainedSamples)
          || v.valid_end_seconds !== Number(BigInt(v.valid_end_counter!) - BigInt(detail.source_origin_counter!)) / c.sample_rate_hz))) {
      throw new Error("Adaptive source times differ from exact counters");
    }
  });
  return detail;
}
