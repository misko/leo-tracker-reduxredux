/* Whole-dwell timing proposals, not a detection verdict or GLRT replacement. */
#ifndef LEO_PRESENCE_WINDOW_RANK_H
#define LEO_PRESENCE_WINDOW_RANK_H
#include "presence.h"

typedef struct leo_presence_rank_workspace leo_presence_rank_workspace;
typedef struct {
    double scores[6];
    uint32_t order[6], projected_epoch_samples[6];
    double fold_cpu_ms, correlation_cpu_ms, total_cpu_ms, total_wall_ms;
} leo_presence_rank_result;

/* Qualified geometry only: one RX, 120 ms at 2.5/5 MS/s. Bins must be a
 * power of two in [512,8192]. Each 20 ms slice is searched independently,
 * without reference epochs/CFOs or previous-dwell state. The proposed epoch
 * is approximate and must NOT replace fractional GLRT confirmation.
 * Setup allocates bounded scratch; run never allocates or retains caller IQ.
 * Workspaces are non-reentrant. Failures leave the result unchanged. */
leo_presence_rank_workspace *leo_presence_rank_create(uint32_t rate_hz,
    const leo_presence_complex *exact, size_t template_count, uint32_t bins);
void leo_presence_rank_destroy(leo_presence_rank_workspace *workspace);
int leo_presence_rank_ci16(leo_presence_rank_workspace *workspace,
    const int16_t *single_rx_iq, size_t sample_count, leo_presence_rank_result *result);
#endif
