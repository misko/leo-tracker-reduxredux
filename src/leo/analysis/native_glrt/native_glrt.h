#ifndef LEO_ANALYSIS_NATIVE_GLRT_H
#define LEO_ANALYSIS_NATIVE_GLRT_H

#include <stddef.h>
#include <stdint.h>

#define LEO_NATIVE_GLRT_MAX_CANDIDATES 8
#define LEO_NATIVE_GLRT_MAX_ROWS 70

typedef struct leo_native_glrt leo_native_glrt;

typedef struct { double real,imaginary; } leo_native_glrt_complex;

typedef struct {
    int32_t coarse_epoch, coarse_bin, refined_epoch, frame_support;
    int32_t glrt_complete, conditioned_fallback, refinement_skipped;
    double coarse_cfo_hz, fine_cfo_hz, conditioned_cfo_hz;
    int32_t epoch;
    double acquired_cfo_hz, tracking_cfo_hz;
    double exact_score, control_score, margin;
    double acquire_score, verify_score, verify_control_score;
    double conditioned_score, coarse_score;
} leo_native_glrt_candidate;

typedef struct {
    int32_t receiver_id, probe_index, probe_start_ms;
    int32_t proposal_executed, proposal_tracking_fallback;
    int32_t proposal_neighbor_matches;
    int32_t candidate_count, retained_peak_count, coarse_gate_skipped_count;
    int32_t conditioned_fallback_count, actual_executed_glrt_calls;
    int32_t glrt_cache_hits, conditioned_cache_hits;
    int32_t fine_fft_cache_entries, fine_fft_cache_hits;
    int32_t fine_precision_calls, fine_precision_guard_checks;
    int32_t fine_precision_fallbacks, fine_precision_nonfinite_fallbacks;
    int32_t fine_precision_near_tie_fallbacks;
    int32_t fine_precision_interpolation_fallbacks;
    int32_t conditioned_bins_screened, conditioned_bins_rechecked;
    double total_cpu_ms, proposal_ms, stage_sum_ms;
    double proposal_fold_ms, proposal_correlation_ms, proposal_ranking_ms;
    double coarse_ms, acquisition_ms, fine_fft_ms, conditioned_ms;
    double verification_ms, glrt_ms;
    leo_native_glrt_candidate candidates[LEO_NATIVE_GLRT_MAX_CANDIDATES];
} leo_native_glrt_row;

typedef struct {
    size_t row_count;
    double detector_cpu_ms;
    leo_native_glrt_row rows[LEO_NATIVE_GLRT_MAX_ROWS];
} leo_native_glrt_result;

enum {
    LEO_NATIVE_GLRT_OK = 0,
    LEO_NATIVE_GLRT_INVALID = -1,
    LEO_NATIVE_GLRT_NOMEM = -2,
    LEO_NATIVE_GLRT_BUSY = -3,
    LEO_NATIVE_GLRT_KERNEL = -4
};

/* The frozen Wave8 kernels contain process-global FFT caches. Create, analyze,
 * and destroy calls are process-serialized; concurrent calls return BUSY. */
int leo_native_glrt_create(leo_native_glrt **out, uint32_t sample_rate_hz,
    const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template, size_t template_complex_count);
int leo_native_glrt_destroy(leo_native_glrt *context);
int leo_native_glrt_layout(uint32_t sample_rate_hz, uint32_t dwell_ms,
    uint32_t probe_stride_ms, size_t *complex_times, size_t *row_count);
int leo_native_glrt_analyze(leo_native_glrt *context,
    const int16_t *dual_rx_iqiq, size_t complex_times,
    uint32_t dwell_ms, uint32_t probe_stride_ms,
    leo_native_glrt_result *result);
const char *leo_native_glrt_status_string(int status);

#endif
