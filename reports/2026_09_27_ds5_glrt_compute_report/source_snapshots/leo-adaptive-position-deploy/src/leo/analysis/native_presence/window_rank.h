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
typedef struct {
    uint32_t epoch;
    double score, fold_cpu_ms, correlation_cpu_ms, total_cpu_ms, total_wall_ms;
} leo_presence_timing_proposal;
/* Private research diagnostics, not a published wire or storage layout.
 * Rows are point interpolation (0) and area average (1). Hybrid selection
 * compares max/second scores, with a 1e-30 denominator floor and point ties.
 * A mask identifies populated rows; scores are NOT calibrated probabilities. */
typedef struct {
    uint32_t available_mask, selected;
    double scores[2][6], contrast[2];
    uint32_t order[2][6], epochs[2][6];
} leo_presence_rank_screens;

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
/* Evaluate exactly one 20ms window at this workspace's grid resolution.
 * Independent of previous rank calls, with unchanged fractional confirmation
 * requirements. Useful for high-resolution timing after a cheap full screen. */
int leo_presence_rank_window_ci16(leo_presence_rank_workspace *workspace,
    const int16_t *single_rx_iq, size_t sample_count, leo_presence_timing_proposal *result);
/* Last successful complete-dwell diagnostics. Any later window/run attempt
 * invalidates them. The single-window API uses point interpolation in a
 * hybrid build: cross-window contrast has no meaning for a single window. */
int leo_presence_rank_get_screens(const leo_presence_rank_workspace *workspace,
    leo_presence_rank_screens *screens);
#endif
