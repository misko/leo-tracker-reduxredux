#ifndef LEO_RESEARCH_SERVER_SIMD_H
#define LEO_RESEARCH_SERVER_SIMD_H

#include "blind_strided_v4.h"

typedef struct leo_blind_strided_v4_workspace leo_server_simd_workspace;

int leo_server_simd_force(int mode);
const char *leo_server_simd_kernel(void);
int leo_server_simd_pack_probe(const int16_t *raw_iq, size_t sample_count,
    uint32_t receiver_lane, int16_t *packed_iq);
leo_server_simd_workspace *leo_server_simd_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins, uint32_t timing_bins);
void leo_server_simd_destroy(leo_server_simd_workspace *workspace);
int leo_server_simd_run_ci16(leo_server_simd_workspace *workspace,
    const int16_t *raw_iq, size_t sample_count, uint32_t receiver_lane,
    uint32_t max_confirmations, uint32_t seeded, leo_presence_dwell_result *result);
int leo_server_simd_get_screens(const leo_server_simd_workspace *workspace,
    leo_presence_rank_screens *screens);

#endif
