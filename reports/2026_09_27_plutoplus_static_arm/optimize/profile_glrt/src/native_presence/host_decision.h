/* Versioned numerical port for native 10M IQ / 2.5M adaptive decisions.
 * No radio, filesystem, scheduler or ownership operations. */
#ifndef LEO_HOST_DECISION_H
#define LEO_HOST_DECISION_H
#include "presence.h"

typedef struct leo_host_decision leo_host_decision;
typedef struct {
    uint32_t version, outcome, screen_mask, confirmation_mask;
    uint32_t supported_start, supported_end, candidate_supported, reserved;
    int32_t epoch, fractional_complete;
    double fractional_offset, cfo_hz, exact_score, margin;
    double filter_cpu_ms, cpu_ms, wall_ms;
    double screen_scores[6];
} leo_host_decision_result_v1;

/* Templates: lower exact/control, upper exact/control, 3333 complex doubles
 * each. Setup copies configuration. A workspace is non-reentrant. */
leo_host_decision *leo_host_decision_create_v1(const leo_presence_complex *templates,
    size_t template_count);
void leo_host_decision_destroy_v1(leo_host_decision *);
/* Exactly 1,200,000 CI16 complex samples, one physical RX in payload column 0.
 * edge 0=lower, 1=upper. Each call resets the FIR; caller IQ is never modified.
 * Result outcome: 0 unknown, 1 detected, 2 evaluated without detection.
 * A failed call returns -1 and leaves output unchanged. */
int leo_host_decision_run_v1(leo_host_decision *, const int16_t *iq,
    size_t count, uint32_t edge, leo_host_decision_result_v1 *);
/* Shared support predicate for qualification and execution. Fractional search
 * uses +/-2 samples. Conservatively require that whole candidate frame start
 * is supported, including its complete fractional search interval. */
int leo_host_decision_supported_v1(uint32_t window, int32_t epoch);
/* V2 accepts one complete 120 ms RX0 dwell at exactly 15 or 20 MS/s and
 * reduces it to the same 2.5 MS/s decision coordinates. */
leo_host_decision *leo_host_decision_create_v2(const leo_presence_complex *templates,
    size_t template_count, uint32_t source_rate_hz);
int leo_host_decision_run_v2(leo_host_decision *, const int16_t *iq,
    size_t count, uint32_t edge, leo_host_decision_result_v1 *);
#endif
