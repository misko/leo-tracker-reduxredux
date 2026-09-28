#ifndef LEO_RESEARCH_FULL_SEARCH_H
#define LEO_RESEARCH_FULL_SEARCH_H

#include <stddef.h>
#include <stdint.h>
#include "presence.h"

#define LEO_FULL_SEARCH_MAX_CANDIDATES 8

typedef struct {
    double score;
    int32_t epoch;
    int32_t coarse_bin;
} leo_full_search_peak;

typedef struct {
    leo_presence_candidate candidate;
    int32_t coarse_epoch;
    int32_t coarse_bin;
    int32_t refined_epoch;
    int32_t frame_support;
    int32_t glrt_complete;
    double coarse_cfo_hz;
    double fine_cfo_hz;
    double conditioned_cfo_hz;
} leo_full_search_candidate;

typedef struct {
    int32_t candidate_count;
    int32_t retained_peak_count;
    leo_full_search_candidate candidates[LEO_FULL_SEARCH_MAX_CANDIDATES];
    double conversion_cpu_ms;
    double coarse_cpu_ms;
    double acquisition_cpu_ms;
    double fine_fft_cpu_ms;
    double conditioned_cpu_ms;
    double verification_cpu_ms;
    int32_t conditioned_bins_screened;
    int32_t conditioned_bins_rechecked;
    double glrt_cpu_ms;
    double total_cpu_ms;
    double total_wall_ms;
} leo_full_search_result;

/* Research-private full candidate inventory. This translation unit includes
 * the frozen native presence implementation and must replace, rather than be
 * linked alongside, a separately compiled presence.c object. */
int leo_full_search_run(leo_presence_workspace *workspace,
    const leo_presence_complex *samples, size_t count,
    leo_full_search_result *result);

/* Pure deterministic helper retained for unit qualification of peak ordering
 * and all-previous basin separation. `peaks` may be in any input order. */
size_t leo_full_search_retain_peaks(leo_full_search_peak *peaks, size_t peak_count,
    int32_t epoch_count, const double coarse_cfo_hz[11],
    leo_full_search_peak retained[LEO_FULL_SEARCH_MAX_CANDIDATES]);

#endif
