#ifndef LEO_ADAPTIVE_CORRECTED_PROFILE_BRIDGE_H
#define LEO_ADAPTIVE_CORRECTED_PROFILE_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_CORRECTED_PROFILE_MAX_CANDIDATES 8
#define LEO_CORRECTED_PROFILE_MAX_ROWS 70

typedef struct leo_corrected_profile_complex {
    double real, imaginary;
} leo_corrected_profile_complex;

/* These value-owned structures contain only fields shared with public detector
 * ABI v1.  The corrected backend has four additional interval diagnostics per
 * row; they deliberately stop at this private boundary. */
typedef struct leo_corrected_profile_candidate_value {
    int32_t coarse_epoch, coarse_bin, refined_epoch, frame_support;
    int32_t glrt_complete, conditioned_fallback, refinement_skipped;
    double coarse_cfo_hz, fine_cfo_hz, conditioned_cfo_hz;
    int32_t epoch;
    double acquired_cfo_hz, tracking_cfo_hz;
    double exact_score, control_score, margin;
    double acquire_score, verify_score, verify_control_score;
    double conditioned_score, coarse_score;
    int32_t fractional_epoch_status;
    double fractional_epoch_offset_samples;
    double fractional_epoch_log_curvature;
    double fractional_epoch_exact_grid[5];
    double fractional_epoch_control_grid[5];
    double fractional_exact_score, fractional_control_score, fractional_margin;
    double fractional_residual_cfo_hz, fractional_tracking_cfo_hz;
} leo_corrected_profile_candidate_value;

typedef struct leo_corrected_profile_row_value {
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
    double verification_ms, glrt_ms, fractional_epoch_ms;
    leo_corrected_profile_candidate_value
        candidates[LEO_CORRECTED_PROFILE_MAX_CANDIDATES];
} leo_corrected_profile_row_value;

typedef struct leo_corrected_profile_result_value {
    size_t row_count;
    double detector_cpu_ms;
    leo_corrected_profile_row_value rows[LEO_CORRECTED_PROFILE_MAX_ROWS];
} leo_corrected_profile_result_value;

typedef struct leo_corrected_profile_backend leo_corrected_profile_backend;

int leo_corrected_profile_backend_create(leo_corrected_profile_backend **out,
    uint32_t sample_rate_hz,
    const leo_corrected_profile_complex *exact_template,
    const leo_corrected_profile_complex *control_template,
    size_t template_complex_count);
int leo_corrected_profile_backend_destroy(leo_corrected_profile_backend *backend);
int leo_corrected_profile_backend_analyze(leo_corrected_profile_backend *backend,
    const double receiver_center_hz[2], double residual_cfo_min_hz,
    double residual_cfo_max_hz, const int16_t *dual_rx_iqiq,
    size_t complex_times, uint32_t dwell_ms, uint32_t probe_stride_ms,
    leo_corrected_profile_result_value *result);

#ifdef __cplusplus
}
#endif
#endif
