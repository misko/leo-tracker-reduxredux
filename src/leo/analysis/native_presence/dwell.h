/* Bounded whole-dwell research execution; no calibrated verdict is implied. */
#ifndef LEO_PRESENCE_DWELL_H
#define LEO_PRESENCE_DWELL_H
#include "window_rank.h"

typedef struct leo_presence_dwell_workspace leo_presence_dwell_workspace;
typedef struct {
    leo_presence_rank_result rank;
    uint32_t confirmation_count, confirmation_window_mask;
    leo_presence_result confirmations[6]; /* in rank.order, not temporal order */
    leo_presence_nuisance nuisances[6];
    double prefix_cpu_ms[6], prefix_wall_ms[6];
    double total_cpu_ms, total_wall_ms;
    leo_presence_timing_proposal timing_proposals[6];
} leo_presence_dwell_result;

leo_presence_dwell_workspace *leo_presence_dwell_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t bins);
leo_presence_dwell_workspace *leo_presence_dwell_create_multires(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins, uint32_t timing_bins);
void leo_presence_dwell_destroy(leo_presence_dwell_workspace *workspace);
int leo_presence_dwell_get_screens(const leo_presence_dwell_workspace *workspace,
    leo_presence_rank_screens *screens);
/* seeded=0 retains the blind timing search as comparator; seeded=1 reuses
 * each selected window's projected timing. Both acquire CFO independently.
 * The complete 120ms screen and up to six confirmations share one execution;
 * prefix timings include screening plus all prior confirmations. Allocation
 * and templates are setup-only. No caller memory or counters are retained.
 * Return -1 leaves result unchanged. Masks describe computation, not absence. */
int leo_presence_dwell_run_ci16(leo_presence_dwell_workspace *workspace,
    const int16_t *single_rx_iq, size_t count, uint32_t max_confirmations,
    uint32_t seeded, leo_presence_dwell_result *result);
#endif
