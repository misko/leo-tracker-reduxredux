#ifndef LEO_RESEARCH_LAG3_PROPOSAL_H
#define LEO_RESEARCH_LAG3_PROPOSAL_H

#include <stddef.h>
#include <stdint.h>

#define LEO_LAG3_PROPOSAL_COUNT 3u
#define LEO_LAG3_PROPOSAL_BINS 512u

typedef struct { double re, im; } leo_lag3_complex;

typedef struct {
    uint32_t window;
    uint32_t integer_epoch;
    uint32_t projected_bin;
    uint32_t phase_valid;
    uint32_t in_declared_cfo_range;
    uint32_t supported;
    uint32_t reserved;
    double phase_cfo_hz;
    double proposal_score;
    double phase_support_score;
    double correlation_re;
    double correlation_im;
} leo_lag3_candidate;

typedef struct {
    leo_lag3_candidate candidates[LEO_LAG3_PROPOSAL_COUNT];
    uint32_t candidate_count;
    uint32_t lag_samples;
    uint32_t bins;
    uint32_t reserved;
    double fold_cpu_ms;
    double correlation_cpu_ms;
    double total_cpu_ms;
    double total_wall_ms;
} leo_lag3_result;

typedef struct leo_lag3_workspace leo_lag3_workspace;

leo_lag3_workspace *leo_lag3_create(uint32_t rate_hz,
    const leo_lag3_complex *exact, size_t template_count);
void leo_lag3_destroy(leo_lag3_workspace *workspace);

/* raw_base points to sample zero in [sample][receiver][I,Q] CI16 storage.
 * count is the sample count, not the int16 count. The required backing span is
 * exactly count*4 int16 values. receiver is 0 or 1. Input is read-only. */
int leo_lag3_run(leo_lag3_workspace *workspace, const int16_t *raw_base,
    size_t count, uint32_t receiver, leo_lag3_result *result);

#endif
