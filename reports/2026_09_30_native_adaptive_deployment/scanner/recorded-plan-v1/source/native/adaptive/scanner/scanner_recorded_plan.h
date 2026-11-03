#ifndef LEO_ADAPTIVE_SCANNER_RECORDED_PLAN_H
#define LEO_ADAPTIVE_SCANNER_RECORDED_PLAN_H

#include "scanner_profile.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_SCANNER_RECORDED_PLAN_ABI_VERSION 1u
#define LEO_SCANNER_RECORDED_PLAN_MAX_VISITS 16384u

typedef struct leo_scanner_recorded_config {
    uint32_t abi_version;
    uint64_t session;
    uint64_t generation;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint64_t wall_deadline_monotonic_ns;
    uint32_t detector_queue_capacity;
    uint32_t target_count;
    leo_scanner_target targets[LEO_SCANNER_MAX_TARGETS];
} leo_scanner_recorded_config;

/* Original source-clock and target authority for one saved visit.  Omitted
 * intervals between rows are outside every dwell; they are not reported as
 * missing samples.  Version 1 requires selection_applied and a 120 ms dwell. */
typedef struct leo_scanner_recorded_visit {
    uint64_t visit;
    uint32_t target_index;
    uint32_t target_key;
    uint32_t dwell_ms;
    uint32_t selection_applied;
    uint32_t expected_transition_flags;
    uint32_t expected_profile_crc32;
    uint64_t requested_frequency_hz;
    uint64_t expected_actual_frequency_hz;
    uint64_t selection_counter;
    uint64_t transition_previous_valid_end;
    uint64_t transition_valid_start;
    uint64_t valid_start;
    uint64_t valid_end;
} leo_scanner_recorded_visit;

typedef struct leo_scanner_recorded_plan {
    uint32_t abi_version;
    uint32_t visit_count;
    const leo_scanner_recorded_visit *visits;
    uint8_t plan_digest[32];
} leo_scanner_recorded_plan;

/* Saved-data composition using the same source capture, geometry derivation,
 * bounded detector slots, executor, and event path as the adaptive scanner.
 * It preserves the supplied global visit IDs and does not execute SPF target
 * selection, feedback, or acknowledgements.  The source transition receipt
 * must match every expected row field exactly. */
int leo_scanner_run_source_profiled_recorded_ex(
    const leo_scanner_recorded_config *config,
    const leo_scanner_recorded_plan *plan,
    leo_source_port *source,
    const leo_scanner_source_requirements *requirements,
    const leo_scanner_profile_execution_options *execution,
    leo_scanner_source_event_sink sink,
    void *sink_context,
    leo_scanner_source_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
