/* Scanner-owned deterministic policy. No IIO, worker ABI, filesystem or clock
 * dependency. One scheduler thread owns a session; callers supply device time.
 * This new API does not change published fixed-hop or GLRT wire contracts. */
#ifndef LEO_ADAPTIVE_SCAN_H
#define LEO_ADAPTIVE_SCAN_H
#include <stdint.h>

#define LEO_ADAPTIVE_MAX_TARGETS 8u
#define LEO_ADAPTIVE_MAX_VISITS 2500u
#define LEO_ADAPTIVE_NO_VISIT UINT64_MAX

enum leo_adaptive_outcome {
    LEO_ADAPTIVE_UNKNOWN, LEO_ADAPTIVE_DETECTED, LEO_ADAPTIVE_NOT_DETECTED
};
enum leo_adaptive_state { LEO_ADAPTIVE_EXPLORING, LEO_ADAPTIVE_ACTIVE, LEO_ADAPTIVE_QUIET };
enum leo_adaptive_reason {
    LEO_ADAPTIVE_WARMUP, LEO_ADAPTIVE_WEIGHTED, LEO_ADAPTIVE_EXPLORATION,
    LEO_ADAPTIVE_NONE_ACTIVE, LEO_ADAPTIVE_FAULT_FALLBACK
};

typedef struct {
    uint64_t session, generation, start_counter;
    uint32_t rate_hz, target_count, maximum_visits;
    uint32_t warmup_visits, missed_dwells, active_weight, quiet_weight;
    uint32_t cooldown_ms, maximum_revisit_ms, hop_budget_ms;
    uint32_t maximum_result_age_ms, unhealthy_limit;
} leo_adaptive_config_v1;

/* A completed configured search with no detection is NOT an absence claim.
 * healthy=1 also permits UNKNOWN (e.g. unbracketed fractional refinement).
 * Transport/worker failure has healthy=0 and must have outcome UNKNOWN. */
typedef struct {
    uint64_t session, generation, visit, valid_start, valid_end;
    uint32_t rate_hz, rx, target, outcome, healthy;
} leo_adaptive_observation_v1;

typedef struct {
    uint64_t visit, decision_counter, basis_visit, cooldown_remaining_samples;
    uint32_t target, reason, active_mask, quiet_mask, consecutive_misses;
} leo_adaptive_choice_v1;

typedef struct {
    uint64_t last_detection_end, last_visit_start;
    uint32_t state, consecutive_misses, visits, has_detection;
} leo_adaptive_target_v1;

typedef struct leo_adaptive_scan leo_adaptive_scan;
/* Allocate once before acquisition. Defaults are explicit at the composition
 * boundary, not hidden in the policy. Output is unchanged on failure. */
int leo_adaptive_create(leo_adaptive_scan **, const leo_adaptive_config_v1 *);
void leo_adaptive_destroy(leo_adaptive_scan *);
/* Copy a result without applying it out of source order. Returns -EALREADY for
 * duplicates or results whose bounded wait expired. Neither rewrites history. */
int leo_adaptive_observe(leo_adaptive_scan *, const leo_adaptive_observation_v1 *,
    uint64_t received_counter);
/* Select once, then commit the actual attested valid interval. No waiting or
 * allocation. At most eight pending observations are applied per selection.
 * A missed exploration deadline is observable; OS/retune lateness cannot be
 * made into a hard realtime guarantee by this policy. */
int leo_adaptive_choose(leo_adaptive_scan *, uint64_t now, leo_adaptive_choice_v1 *);
int leo_adaptive_commit(leo_adaptive_scan *, uint64_t valid_start, uint64_t valid_end);
/* Shadow/external-selection port: charge the visit to the ACTUAL target, not
 * the pending recommendation. Future decisions and observation binding then
 * use only executed visits. Does not claim an unsampled counterfactual. */
int leo_adaptive_commit_actual(leo_adaptive_scan *, uint32_t actual_target,
    uint64_t valid_start, uint64_t valid_end);
/* Serious feedback faults latch fixed-order scanning until session destruction.
 * It remains the SAME recording/session; no wire-mode change or RX restart. */
void leo_adaptive_fallback(leo_adaptive_scan *);
int leo_adaptive_target(const leo_adaptive_scan *, uint32_t target, leo_adaptive_target_v1 *);
#endif
