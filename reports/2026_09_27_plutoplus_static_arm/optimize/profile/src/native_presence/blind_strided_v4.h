#ifndef LEO_RESEARCH_BLIND_STRIDED_V4_H
#define LEO_RESEARCH_BLIND_STRIDED_V4_H

#include "dwell.h"

typedef struct leo_blind_strided_v4_workspace leo_blind_strided_v4_workspace;

/* Research-only exact-equivalent ingress for a selected receiver view. The
 * stride is measured in int16 elements between successive complex samples.
 * The caller must provide readable backing storage through int16 offset
 * (sample_count-1)*sample_stride_i16+1 from receiver_iq. Rank reads that span
 * directly. Only a selected 20 ms interval is packed before invoking the
 * unchanged confirmation API. */
leo_blind_strided_v4_workspace *leo_blind_strided_v4_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins, uint32_t timing_bins);
void leo_blind_strided_v4_destroy(leo_blind_strided_v4_workspace *workspace);
int leo_blind_strided_v4_run_ci16(leo_blind_strided_v4_workspace *workspace,
    const int16_t *receiver_iq, size_t sample_count, uint32_t sample_stride_i16,
    uint32_t max_confirmations, uint32_t seeded, leo_presence_dwell_result *result);
int leo_blind_strided_v4_get_screens(
    const leo_blind_strided_v4_workspace *workspace,
    leo_presence_rank_screens *screens);

#endif
