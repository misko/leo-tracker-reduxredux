/* Research-only 10M recorded-IQ -> 5M progressive decision experiment.
 * No IIO, worker IPC, production protocol or calibrated absence claim. */
#ifndef LEO_PROGRESSIVE_DECISION_H
#define LEO_PROGRESSIVE_DECISION_H
#include "presence.h"
typedef struct leo_progressive_workspace leo_progressive_workspace;
typedef struct {
    uint32_t probes, mask, positive_mask, outcome, budget_exceeded;
    /* outcome: 0 unknown, 1 positive, 2 all-six evaluated without positive. */
    double filter_cpu_ms, confirm_cpu_ms, total_cpu_ms, total_wall_ms;
    double probe_cpu_ms[6];
    leo_presence_result confirmations[6]; /* temporal window index */
} leo_progressive_result;
leo_progressive_workspace *leo_progressive_create(const leo_presence_complex *exact,
    const leo_presence_complex *control, size_t count, const float taps[129]);
void leo_progressive_destroy(leo_progressive_workspace *w);
int leo_progressive_filter(const int16_t *iq, size_t count, unsigned window,
    const float taps[129], int16_t *out);
/* budget_ms=0 evaluates without a compute budget. A positive stops expansion.
 * A nonpreemptible probe may overrun the soft CPU budget. Such a result is
 * UNKNOWN and explicitly flagged; this API does not promise a hard deadline. */
int leo_progressive_run(leo_progressive_workspace *w, const int16_t *iq,
    size_t count, double budget_ms, leo_progressive_result *out);
#endif
