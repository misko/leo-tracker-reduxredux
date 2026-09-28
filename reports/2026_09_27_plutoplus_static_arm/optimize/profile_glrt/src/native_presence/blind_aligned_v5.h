#ifndef LEO_RESEARCH_BLIND_ALIGNED_V5_H
#define LEO_RESEARCH_BLIND_ALIGNED_V5_H

#include "blind_strided_v4.h"

typedef struct leo_blind_strided_v4_workspace leo_blind_aligned_v5_workspace;

/* Research-only dual-RX ingress. raw_iq begins at RX0 I for sample zero and
 * has the fixed [sample][receiver][I/Q] CI16 layout: exactly four int16 values
 * per sample. receiver_lane is 0 or 1. The readable backing span is therefore
 * exactly 4*sample_count int16 values. This alignment lets ARM NEON use vld4
 * without reading beyond the final sample or shifting an RX1 pointer. */
leo_blind_aligned_v5_workspace *leo_blind_aligned_v5_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins, uint32_t timing_bins);
void leo_blind_aligned_v5_destroy(leo_blind_aligned_v5_workspace *workspace);
int leo_blind_aligned_v5_run_ci16(leo_blind_aligned_v5_workspace *workspace,
    const int16_t *raw_iq, size_t sample_count, uint32_t receiver_lane,
    uint32_t max_confirmations, uint32_t seeded, leo_presence_dwell_result *result);
int leo_blind_aligned_v5_get_screens(
    const leo_blind_aligned_v5_workspace *workspace,
    leo_presence_rank_screens *screens);
/* Post-run diagnostic for the selected confirmation only.  This is outside
 * the detector timing interval and does not alter its result or workspace. */
int leo_blind_aligned_v5_get_profile(
    const leo_blind_aligned_v5_workspace *workspace,
    leo_presence_profile *profile);
int leo_blind_aligned_v5_get_glrt_profile(
    const leo_blind_aligned_v5_workspace *workspace,
    leo_presence_glrt_profile *profile);

#endif
