#ifndef LEO_RESEARCH_GLRT_TRACK_H
#define LEO_RESEARCH_GLRT_TRACK_H

#include <stddef.h>
#include <stdint.h>
#include "../2026_09_28_arm_full_optimization/full_search.h"

#define LEO_TRACK_MAX_CANDIDATES LEO_FULL_SEARCH_MAX_CANDIDATES
#define LEO_TRACK_POSITIVE_MARGIN 0.025

typedef struct {
    int32_t seed_rank;
    int32_t epoch;
    int32_t epoch_delta;
    int32_t glrt_complete;
    int32_t acquisition_fields_valid;
    int32_t coarse_fields_valid;
    int32_t verification_fields_valid;
    double acquired_cfo_hz;
    double tracking_cfo_hz;
    double exact_score;
    double control_score;
    double margin;
} leo_tracking_candidate;

typedef struct {
    int32_t candidate_count;
    leo_tracking_candidate candidates[LEO_TRACK_MAX_CANDIDATES];
} leo_tracking_state;

typedef struct {
    int32_t candidate_count;
    int32_t positive_count;
    int32_t candidate_eval_attempts;
    leo_tracking_candidate candidates[LEO_TRACK_MAX_CANDIDATES];
    double conversion_cpu_ms;
    double coarse_cpu_ms;
    double acquisition_cpu_ms;
    double fine_fft_cpu_ms;
    double conditioned_cpu_ms;
    double verification_cpu_ms;
    double glrt_cpu_ms;
    double total_cpu_ms;
} leo_tracking_result;

typedef struct leo_tracking_workspace leo_tracking_workspace;

leo_tracking_workspace *leo_tracking_create(uint32_t rate_hz,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count);
void leo_tracking_destroy(leo_tracking_workspace *workspace);
void leo_tracking_state_reset(leo_tracking_state *state);
int leo_tracking_state_set(leo_tracking_state *state,
    const leo_tracking_candidate *candidates, size_t count);

/* Window-local epoch propagation across an absolute 10 ms input shift. */
int32_t leo_tracking_propagate_epoch(uint32_t rate_hz, int32_t epoch);
int32_t leo_tracking_wrap_epoch(int32_t epoch, int32_t delta, int32_t period_cells);

/* Refresh performs the complete eight-candidate search. Follow ingests one
 * 20 ms window, evaluates each prior seed at propagated epoch +/- radius, and
 * retains one best integer-epoch GLRT result per seed without deduplication. */
int leo_tracking_refresh(leo_tracking_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    leo_tracking_state *state, leo_tracking_result *result);
int leo_tracking_follow(leo_tracking_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    leo_tracking_state *state, int radius, leo_tracking_result *result);

#endif
