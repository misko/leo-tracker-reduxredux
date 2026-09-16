import type { AdaptiveDetail, AdaptivePage, HostAdaptiveCapture, HostAdaptiveCaptureV3 } from "./adaptive-api";

// Synthetic metadata only; not RF evidence or a quality/performance fixture.
export function adaptiveDetailFixture(sessionId = "adaptive-test", count = 54): AdaptiveDetail {
  const origin = 9007199254741011n;
  const rate = 2500000;
  const visits: AdaptiveDetail["visits"] = Array.from({ length: count }, (_, i) => {
    const start = origin + BigInt(i * 400000 + 100000);
    const retained = i < count - 1;
    return {
      visit_index: i, target_index: i % 8, proposed_target_index: (i + 3) % 8,
      retained, invalid_start_seconds: i * 400000 / rate,
      valid_start_seconds: Number(start - origin) / rate,
      valid_end_seconds: retained ? Number(start + 300000n - origin) / rate : null,
      valid_start_counter: String(start), valid_end_counter: retained ? String(start + 300000n) : null,
      decision_counter: String(start - 100000n), basis_visit: i ? i - 1 : null,
      reason: i < 24 ? "warmup" : "fault_fallback", active_mask: i < 24 ? 0 : 13,
      quiet_mask: i < 24 ? 0 : 242, consecutive_misses: i < 24 ? 0 : 2,
      cooldown_remaining_seconds: i < 24 ? 0 : 1.5,
    };
  });
  return {
    schema_version: 1, kind: "adaptive_hop_session_detail", source_origin_counter: count ? String(origin) : null,
    capture: {
      schema_version: 1, kind: "adaptive_hop_history_item", session_id: sessionId,
      input_manifest_sha256: `sha256:${"c".repeat(64)}`, radio_id: "synthetic-radio",
      mode: "shadow", policy_generation: "71", recorded_at: "2026-09-09T00:00:00Z",
      finalized_at: "2026-09-09T00:05:00Z", captured_at: count ? "2026-09-09T00:00:00Z" : null,
      utc_qualified: !!count, utc_bracket_width_ms: count ? 1 : null,
      nominal_duration_seconds: 300, valid_visit_ms: 120, sample_rate_hz: rate, bandwidth_hz: rate,
      started_visits: count, retained_visits: Math.max(0, count - 1), source_span_attested: !!count,
      source_span_seconds: count ? count * .16 : null, valid_duty_ppm: count ? 720000 : null,
      capture_qualified: false, terminal_state: "cancelled", restoration_status: "restored",
      fallback_choices: Math.max(0, count - 24), analysis_state: "not_integrated",
      target_coverage: Array.from({ length: 8 }, (_, i) => {
        const retained = visits.filter(v => v.retained && v.target_index === i);
        return {
          target_index: i, target: { channel: i % 4 + 1, edge: i < 4 ? "lower" : "upper", rf_center_hz: 10e9 + i * 1e8, if_center_hz: 1e9 + i * 1e8 },
          retained_visits: retained.length, valid_seconds: retained.length * .12,
          allocation_ppm: count > 1 ? Math.floor(retained.length * 1000000 / (count - 1)) : null,
          maximum_revisit_seconds: retained.length > 1 ? 1.28 : null,
          maximum_unobserved_seconds: count ? 1.2 : null,
        };
      }),
    }, visits,
  };
}

export function adaptivePageFixture(detail = adaptiveDetailFixture()): AdaptivePage {
  return { schema_version: 1, kind: "adaptive_hop_history_page", cursor: 0, limit: 5, total: 1, next_cursor: null, items: [detail.capture] };
}

export function hostAdaptiveDetailFixture(receiver: 0 | 1 = 0): AdaptiveDetail & { capture: HostAdaptiveCapture } {
  const legacy = adaptiveDetailFixture();
  const origin = BigInt(legacy.source_origin_counter!);
  const scale = (counter: string) => String(origin + (BigInt(counter) - origin) * 4n);
  const count = legacy.capture.retained_visits;
  return { ...legacy, schema_version: 2,
    visits: legacy.visits.map(v => ({ ...v, valid_start_counter: scale(v.valid_start_counter),
      valid_end_counter: v.valid_end_counter === null ? null : scale(v.valid_end_counter), decision_counter: scale(v.decision_counter) })),
    capture: { ...legacy.capture, schema_version: 2, sample_rate_hz: 10000000, bandwidth_hz: 10000000,
      analysis_state: "separate_product", radio_serial: "104000bac4950008230026001b440a003a", physical_receiver: receiver,
      decision_configuration: { schema_version: 1, execution: "host", source_rate_hz: 10000000, decision_rate_hz: 2500000,
        decimation_factor: 4, filter_taps: 161, screen_count: 6, maximum_confirmations: 1, detector_manifest_sha256: `sha256:${"a".repeat(64)}` },
      host_feedback: { schema_version: 1, complete_visits: count, healthy: count - 1, degraded: 1, unknown_feedback: 1,
        accepted: count - 1, source_ended: 1, rejected: 0, not_submitted: 0, maximum_host_result_age_ms: 129,
        maximum_feedback_call_ms: 3, first_feedback_error: null } },
    host_decisions: Array.from({ length: count }, (_, i) => ({ schema_version: 1, visit_index: i,
      health: i === count - 1 ? "queue_overflow" : "healthy", failure: i === count - 1 ? "Queue full" : null,
      feedback_error: null, feedback_outcome: i === count - 1 ? "unknown" : "not_detected",
      feedback_disposition: i === count - 1 ? "source_ended" : "accepted", host_result_age_ms: 129,
      worker_elapsed_ms: i === count - 1 ? null : 38, feedback_call_ms: 3,
      numerics: i === count - 1 ? null : { schema_version: 1, outcome: "not_detected", screen_mask: 63,
        confirmation_mask: 4, supported_start: 40, supported_end: 300000, screen_scores: [.01, .02, .03, .01, .02, .01],
        candidate_supported: true, fractional_complete: true } })),
  };
}

export function multirateAdaptiveDetailFixture(rate: 15000000 | 20000000): AdaptiveDetail & { capture: HostAdaptiveCaptureV3 } {
  const legacy = adaptiveDetailFixture();
  const origin = BigInt(legacy.source_origin_counter!);
  const factor = BigInt(rate / 2_500_000);
  const scale = (counter: string) => String(origin + (BigInt(counter) - origin) * factor);
  const count = legacy.capture.retained_visits;
  const geometry = rate === 15000000
    ? { decimation_factor: 6 as const, filter_taps: 201 as const }
    : { decimation_factor: 8 as const, filter_taps: 257 as const };
  const visits = legacy.visits.map((v, i) => {
    const validStart = scale(v.valid_start_counter);
    const retained = i === 7 ? false : i === legacy.visits.length - 1 ? true : v.retained;
    const validEnd = retained ? String(BigInt(validStart) + BigInt(rate * .12)) : null;
    return { ...v, retained, valid_start_counter: validStart,
      valid_end_counter: validEnd, decision_counter: scale(v.decision_counter),
      valid_end_seconds: validEnd === null ? null : Number(BigInt(validEnd) - origin) / rate };
  });
  const retainedIndices = visits.filter(v => v.retained).map(v => v.visit_index);
  return { ...legacy, schema_version: 3,
    visits,
    capture: { ...legacy.capture, schema_version: 3, sample_rate_hz: rate, bandwidth_hz: rate,
      analysis_state: "separate_product", radio_serial: "104000bac4950008230026001b440a003a", physical_receiver: 0,
      decision_configuration: { schema_version: 2, execution: "host", source_rate_hz: rate, decision_rate_hz: 2500000,
        ...geometry, screen_count: 6, maximum_confirmations: 1, detector_manifest_sha256: `sha256:${"a".repeat(64)}` },
      host_feedback: { schema_version: 1, complete_visits: count, healthy: count - 1, degraded: 1, unknown_feedback: 1,
        accepted: count - 1, source_ended: 1, rejected: 0, not_submitted: 0, maximum_host_result_age_ms: 129,
        maximum_feedback_call_ms: 3, first_feedback_error: null } },
    host_decisions: retainedIndices.map((visitIndex, i) => ({ schema_version: 2, visit_index: visitIndex,
      health: i === count - 1 ? "queue_overflow" : "healthy", failure: i === count - 1 ? "Queue full" : null,
      feedback_error: null, feedback_outcome: i === count - 1 ? "unknown" : "not_detected",
      feedback_disposition: i === count - 1 ? "source_ended" : "accepted", host_result_age_ms: 129,
      worker_elapsed_ms: i === count - 1 ? null : 38, feedback_call_ms: 3,
      numerics: i === count - 1 ? null : { schema_version: 2, source_rate_hz: rate, outcome: "not_detected", screen_mask: 63,
        confirmation_mask: 4, supported_start: rate === 15000000 ? 34 : 32, supported_end: 300000, screen_scores: [.01, .02, .03, .01, .02, .01],
        candidate_supported: true, fractional_complete: true } })),
  };
}
