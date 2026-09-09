import type { AdaptiveDetail, AdaptivePage } from "./adaptive-api";

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
