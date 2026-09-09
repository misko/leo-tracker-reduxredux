/* Scanner-owned adapter between the private worker ABI and published records.
 * No IIO, allocation, waiting, or hardware authority. Config identity belongs
 * in the enclosing frame. An enable flag is NOT evidence of qualification. */
#ifndef LEO_SCANNER_GLRT_FRAME_RESULT_H
#define LEO_SCANNER_GLRT_FRAME_RESULT_H
#include "frame_codec.h"
#include "pool.h"
#include "adaptive_scan.h"

typedef struct {
    double minimum_exact_score, minimum_margin;
    /* Set only by a separately reviewed, digest-pinned deployment policy.
     * No policy is enabled by this library. Absence needs its own whole-dwell
     * sensitivity qualification, not just six screen coverage bits. */
    uint32_t classification_enabled, absence_enabled;
} leo_glrt_decision_policy;

/* NULL policy: retain candidate evidence as UNQUALIFIED_CLASSIFIER. Malformed
 * input returns -1 with output unchanged. A computed search without a complete
 * fractional candidate remains INCOMPLETE_SEARCH unless qualified absence is
 * enabled and the search returned no candidates at all. */
int leo_glrt_result_record(const leo_probe_result *, const leo_glrt_decision_policy *,
    leo_glrt_classification_v1 *output);
/* Capture/supervisor failures have no worker result. Emit an explicit unknown
 * for a valid source dwell without inventing searched samples or measurements. */
int leo_glrt_unavailable_record(const leo_probe_request *, enum leo_glrt_reason,
    leo_glrt_classification_v1 *output);
/* Positive-only scheduling evidence. Requires an explicit enabled policy with
 * absence disabled. A successful configured search with no candidate/passing
 * candidate is NOT_DETECTED, never a public NO_SIGNAL claim. Incomplete
 * fractional work is UNKNOWN unless another valid candidate is positive. */
int leo_glrt_result_observation(const leo_probe_result *, const leo_glrt_decision_policy *,
    leo_adaptive_observation_v1 *output);
#endif
