#ifndef LEO_ADAPTIVE_SCANNER_H
#define LEO_ADAPTIVE_SCANNER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
#include "../detector/native_glrt.h"
#ifdef __cplusplus
}
#endif
#include "../device/local/local_source.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_SCANNER_ABI_VERSION 2u
#define LEO_SCANNER_EXECUTION_ABI_VERSION 1u
#define LEO_SCANNER_MAX_TARGETS 8u
#define LEO_SCANNER_MAX_DETECTOR_WORKERS 4u

enum leo_scanner_event_kind {
    LEO_SCANNER_VISIT = 1,
    LEO_SCANNER_QUEUE_DROP = 2,
    LEO_SCANNER_DETECTOR_FAILURE = 3,
    LEO_SCANNER_DETECTOR_RESULT = 4,
    LEO_SCANNER_CANDIDATE = 5,
    LEO_SCANNER_POLICY_ACK = 6
};

enum leo_scanner_feedback_outcome {
    LEO_SCANNER_UNKNOWN = 0,
    LEO_SCANNER_ACTIVE = 1,
    LEO_SCANNER_QUIET = 2
};

enum leo_scanner_stop_reason {
    LEO_SCANNER_STOP_NONE = 0,
    LEO_SCANNER_STOP_SOURCE_DURATION = 1,
    LEO_SCANNER_STOP_MAXIMUM_VISITS = 2,
    LEO_SCANNER_STOP_POLICY_COMPLETE = 3,
    LEO_SCANNER_STOP_WALL_DEADLINE = 4,
    LEO_SCANNER_STOP_SOURCE_ERROR = 5,
    LEO_SCANNER_STOP_POLICY_ERROR = 6,
    LEO_SCANNER_STOP_DETECTOR_ERROR = 7,
    LEO_SCANNER_STOP_INTERNAL_ERROR = 8
};

typedef struct leo_scanner_target {
    uint32_t profile;
    uint64_t frequency_hz;
    uint32_t profile_crc32;
    uint32_t baseline_weight;
} leo_scanner_target;

typedef struct leo_scanner_config {
    uint32_t abi_version;
    uint64_t session;
    uint64_t generation;
    uint64_t seed;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t duration_ms;
    uint32_t maximum_visits;
    /* Absolute CLOCK_MONOTONIC deadline. Required; the scanner cancels a
     * blocking source acquire at this boundary. */
    uint64_t wall_deadline_monotonic_ns;
    /* ACTIVE dwell ceiling. An inactive target uses 120 ms; accepted ACTIVE
     * feedback changes its later visits to this 120/240/360 ms value. */
    uint32_t dwell_ms;
    uint32_t transition_budget_ms;
    uint32_t maximum_revisit_ms;
    uint32_t feedback_age_ms;
    uint32_t application_delay_ms;
    uint32_t decay_ms;
    uint32_t maximum_boost;
    uint32_t detector_queue_capacity;
    /* Source-owned ci16-mean-complex-power-v1 configuration. The deployed
     * policy is exactly -38.0 dBFS and validation rejects any other value. */
    double active_threshold_dbfs;
    uint32_t target_count;
    leo_scanner_target targets[LEO_SCANNER_MAX_TARGETS];
} leo_scanner_config;

typedef struct leo_scanner_detector_ops {
    void *context;
    int (*analyze)(void *context, const int16_t *dual_rx_iqiq,
        size_t complex_times, uint32_t dwell_ms, uint32_t probe_stride_ms,
        leo_native_glrt_result *result);
    int (*capabilities)(void *context, leo_native_glrt_capabilities *capabilities);
} leo_scanner_detector_ops;

/* A detector binding is borrowed for the complete call, including executor
 * drain. configuration_digest is a caller attestation over the detector
 * build/algorithm, sample rate, exact and control template hashes, and selected
 * mode. The scanner checks that all digests match; it cannot inspect or verify
 * the detector contexts against that attestation. */
typedef struct leo_scanner_detector_binding {
    uint32_t abi_version;
    leo_scanner_detector_ops ops;
    uint8_t configuration_digest[32];
} leo_scanner_detector_binding;

/* New execution entrypoints require 1..4 non-null, distinct detector contexts.
 * Every binding must have the same attested configuration and reported
 * capabilities. The caller constructs contexts before the call and destroys
 * them only after it returns. */
typedef struct leo_scanner_execution_options {
    uint32_t abi_version;
    uint32_t detector_worker_count;
    const leo_scanner_detector_binding *detectors;
} leo_scanner_execution_options;

/* Optional counter acquisition port for compositions that must bracket the
 * exact source counter with another clock. The callback runs synchronously on
 * the acquisition/calling thread, first to establish the policy origin and
 * then immediately before every policy selection. No source block is leased
 * during a call. It must return the coherent counter to use for that policy
 * decision; the scanner does not take a second snapshot. Return zero on
 * success or a negative errno-style status on failure. Unexpected positive
 * statuses are normalized to -EIO. The table and its context remain
 * caller-owned and must outlive leo_scanner_run_timed. */
typedef struct leo_scanner_counter_ops {
    void *context;
    int (*snapshot)(void *context, uint64_t *counter);
} leo_scanner_counter_ops;

/* candidate is populated only for LEO_SCANNER_CANDIDATE. UTC fields are absent
 * by design: the local source currently supplies counters, not a UTC bracket. */
typedef struct leo_scanner_event {
    uint32_t kind;
    uint64_t visit;
    uint64_t valid_start;
    uint64_t valid_end;
    uint64_t selection_counter;
    uint64_t transition_counter_before;
    uint64_t transition_counter_after;
    uint32_t recalled;
    uint32_t target;
    uint32_t profile;
    uint32_t attested_profile_crc32;
    uint64_t frequency_hz;
    uint32_t feedback_outcome;
    uint64_t energy_sum;
    uint64_t energy_sample_count;
    double power_dbfs;
    uint32_t windows_emitted;
    uint32_t row_index;
    uint32_t candidate_index;
    int32_t receiver_id;
    int32_t probe_index;
    int32_t detector_status;
    uint32_t fractional_epoch_server_parity_qualified;
    /* CLOCK_MONOTONIC telemetry for detector-lane events. Zero for visits,
     * policy acknowledgements, and drops rejected before enqueue. */
    uint64_t detector_enqueued_monotonic_ns;
    uint64_t detector_started_monotonic_ns;
    uint64_t detector_finished_monotonic_ns;
    uint64_t detector_queue_ns;
    uint64_t detector_runtime_ns;
    uint32_t detector_row_count;
    leo_native_glrt_candidate candidate;
} leo_scanner_event;

/* Sink calls are serialized, but may originate on the acquisition thread or
 * a detector worker. Cross-visit completion order is unspecified. Events for
 * one detector result preserve RESULT-before-CANDIDATE order, though another
 * visit's events may occur between them. The event and embedded values are borrowed
 * only for the duration of the call. */
typedef void (*leo_scanner_event_sink)(void *context,
    const leo_scanner_event *event);

typedef struct leo_scanner_stats {
    uint64_t visits_started;
    uint64_t visits_intact;
    uint64_t visits_incomplete;
    uint64_t windows_emitted;
    uint64_t detector_accepted;
    uint64_t detector_completed;
    uint64_t detector_failures;
    uint64_t detector_queue_drops;
    uint64_t detector_rows;
    uint64_t detector_candidates;
    uint64_t feedback_active;
    uint64_t feedback_quiet;
    uint64_t feedback_unknown;
    uint64_t feedback_rejected;
    uint64_t policy_acks;
    uint64_t missing_samples;
    size_t detector_queue_high_water;
    uint32_t stop_reason;
    int32_t stop_status;
} leo_scanner_stats;

/* source must already be opened and primed and remains caller-owned. This call
 * exclusively recalls/acquires/releases it until completion. Acquisition is
 * deadline bounded: duration_ms is required and capped at 30 minutes,
 * maximum_visits is required, and the watchdog cancels a blocking source call.
 * Completion also requires detector and sink callbacks to return; their ABIs
 * are cooperative and cannot be preempted. The detector lane has one worker. */
int leo_scanner_run(const leo_scanner_config *config,
    leo_local_source *source,
    const leo_scanner_detector_ops *detector,
    leo_scanner_event_sink sink,
    void *sink_context,
    leo_scanner_stats *stats);

/* Additive timed composition. This has the same source ownership, detector,
 * deadline, and event semantics as leo_scanner_run. A counter callback error
 * fails closed as LEO_SCANNER_STOP_SOURCE_ERROR before policy selection or
 * retune at that boundary. The callback is cooperative and must return; source
 * cancellation cannot preempt arbitrary callback code. */
int leo_scanner_run_timed(const leo_scanner_config *config,
    leo_local_source *source,
    const leo_scanner_counter_ops *counter,
    const leo_scanner_detector_ops *detector,
    leo_scanner_event_sink sink,
    void *sink_context,
    leo_scanner_stats *stats);

/* Additive multi-context forms. All execution/configuration validation,
 * including detector capability callbacks, completes before the first source
 * operation. Accepted detector jobs and sink callbacks are drained before
 * return. Queue high-water remains queued-only; active workers are excluded. */
int leo_scanner_run_ex(const leo_scanner_config *config,
    leo_local_source *source,
    const leo_scanner_execution_options *execution,
    leo_scanner_event_sink sink,
    void *sink_context,
    leo_scanner_stats *stats);

int leo_scanner_run_timed_ex(const leo_scanner_config *config,
    leo_local_source *source,
    const leo_scanner_counter_ops *counter,
    const leo_scanner_execution_options *execution,
    leo_scanner_event_sink sink,
    void *sink_context,
    leo_scanner_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
