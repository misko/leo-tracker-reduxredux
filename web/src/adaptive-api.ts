export interface AdaptiveCoverage {
  target_index: number;
  target: { channel: number; edge: "lower" | "upper"; rf_center_hz: number; if_center_hz: number };
  retained_visits: number;
  valid_seconds: number;
  allocation_ppm: number | null;
  maximum_revisit_seconds: number | null;
  maximum_unobserved_seconds: number | null;
}

export interface AdaptiveCapture {
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
  schema_version: 1; kind: "adaptive_hop_history_page";
  cursor: number; limit: number; total: number; next_cursor: number | null;
  items: AdaptiveCapture[];
}

export interface AdaptiveDetail {
  schema_version: 1; kind: "adaptive_hop_session_detail";
  capture: AdaptiveCapture; source_origin_counter: string | null; visits: AdaptiveVisit[];
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

function validateCapture(c: AdaptiveCapture): void {
  if (!c || c.kind !== "adaptive_hop_history_item" || c.schema_version !== 1
      || typeof c.session_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(c.session_id)
      || !/^sha256:[0-9a-f]{64}$/.test(c.input_manifest_sha256) || !counter(c.policy_generation)
      || !["adaptive", "shadow"].includes(c.mode) || typeof c.radio_id !== "string"
      || ![c.recorded_at, c.finalized_at].every(v => typeof v === "string" && Number.isFinite(Date.parse(v)))
      || (c.captured_at !== null && (typeof c.captured_at !== "string" || !Number.isFinite(Date.parse(c.captured_at))))
      || c.nominal_duration_seconds !== 300 || c.valid_visit_ms !== 120
      || ![2500000, 5000000].includes(c.sample_rate_hz) || c.bandwidth_hz !== c.sample_rate_hz
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
      || c.analysis_state !== "not_integrated" || !Array.isArray(c.target_coverage) || c.target_coverage.length !== 8) {
    throw new Error("Adaptive capture evidence is invalid");
  }
  c.target_coverage.forEach((row, i) => {
    if (!row || row.target_index !== i || !row.target || row.target.channel !== i % 4 + 1
        || row.target.edge !== (i < 4 ? "lower" : "upper")
        || !seconds(row.target.rf_center_hz) || !seconds(row.target.if_center_hz)
        || !integer(row.retained_visits, c.retained_visits) || !seconds(row.valid_seconds)
        || (row.allocation_ppm !== null && !integer(row.allocation_ppm, 1000000))
        || !optionalSeconds(row.maximum_revisit_seconds) || !optionalSeconds(row.maximum_unobserved_seconds)) {
      throw new Error("Adaptive coverage evidence is invalid");
    }
  });
  if (c.target_coverage.reduce((sum, row) => sum + row.retained_visits, 0) !== c.retained_visits) {
    throw new Error("Adaptive coverage inventory differs");
  }
}

export async function getAdaptiveSessions(cursor: number, signal?: AbortSignal): Promise<AdaptivePage | null> {
  const response = await fetch(`/api/v1/scanner/adaptive-sessions?cursor=${cursor}&limit=5`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Adaptive history request failed (${response.status})`);
  const page = await response.json() as AdaptivePage;
  if (!page || page.schema_version !== 1 || page.kind !== "adaptive_hop_history_page"
      || page.cursor !== cursor || page.limit !== 5 || !integer(page.total)
      || !Array.isArray(page.items) || page.items.length > page.limit
      || (page.next_cursor !== null && page.next_cursor !== cursor + page.limit)) {
    throw new Error("Adaptive history response is invalid");
  }
  page.items.forEach(validateCapture);
  return page;
}

export async function getAdaptiveSession(sessionId: string, signal?: AbortSignal): Promise<AdaptiveDetail> {
  const response = await fetch(`/api/v1/scanner/adaptive-sessions/${encodeURIComponent(sessionId)}`, { signal });
  if (!response.ok) throw new Error(`Adaptive detail request failed (${response.status})`);
  const detail = await response.json() as AdaptiveDetail;
  if (!detail || detail.schema_version !== 1 || detail.kind !== "adaptive_hop_session_detail") {
    throw new Error("Adaptive detail response is invalid");
  }
  validateCapture(detail.capture);
  const c = detail.capture;
  if (c.session_id !== sessionId || !Array.isArray(detail.visits) || detail.visits.length !== c.started_visits
      || (c.source_span_attested ? !counter(detail.source_origin_counter) : detail.source_origin_counter !== null)) {
    throw new Error("Adaptive detail source binding is invalid");
  }
  detail.visits.forEach((v, i) => {
    if (!v || v.visit_index !== i || !integer(v.target_index, 7) || !integer(v.proposed_target_index, 7)
        || v.retained !== (i < c.retained_visits) || !counter(v.valid_start_counter) || !counter(v.decision_counter)
        || (v.retained ? !counter(v.valid_end_counter) : v.valid_end_counter !== null)
        || !seconds(v.invalid_start_seconds) || !seconds(v.valid_start_seconds)
        || (v.retained ? !seconds(v.valid_end_seconds) || v.valid_end_seconds <= v.valid_start_seconds : v.valid_end_seconds !== null)
        || (v.basis_visit !== null && !integer(v.basis_visit, i - 1))
        || !integer(v.active_mask, 255) || !integer(v.quiet_mask, 255) || (v.active_mask & v.quiet_mask) !== 0
        || !integer(v.consecutive_misses, 3) || !seconds(v.cooldown_remaining_seconds)
        || !["warmup", "weighted", "exploration", "none_active", "fault_fallback"].includes(v.reason)
        || (c.mode === "adaptive" && v.target_index !== v.proposed_target_index)
        || (c.mode === "shadow" && v.target_index !== i % 8)) {
      throw new Error("Adaptive visit evidence is invalid");
    }
    const relative = Number(BigInt(v.valid_start_counter) - BigInt(detail.source_origin_counter!)) / c.sample_rate_hz;
    if (relative !== v.valid_start_seconds || v.invalid_start_seconds > relative
        || BigInt(v.decision_counter) > BigInt(v.valid_start_counter)
        || (v.retained && (BigInt(v.valid_end_counter!) - BigInt(v.valid_start_counter) !== BigInt(c.sample_rate_hz * .12)
          || v.valid_end_seconds !== Number(BigInt(v.valid_end_counter!) - BigInt(detail.source_origin_counter!)) / c.sample_rate_hz))) {
      throw new Error("Adaptive source times differ from exact counters");
    }
  });
  return detail;
}
