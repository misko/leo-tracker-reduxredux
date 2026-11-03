#ifndef LEO_ANALYSIS_NATIVE_GLRT_H
#define LEO_ANALYSIS_NATIVE_GLRT_H

#include <stddef.h>
#include <stdint.h>

#define LEO_NATIVE_GLRT_MAX_CANDIDATES 8
#define LEO_NATIVE_GLRT_MAX_ROWS 70
#define LEO_NATIVE_GLRT_ABI_VERSION 1u

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
    /* 0=not evaluated, 1=complete, 2=unbracketed. Values other than the five
     * score grids are available only when status is complete. */
    int32_t fractional_epoch_status;
    double fractional_epoch_offset_samples;
    double fractional_epoch_log_curvature;
    double fractional_epoch_exact_grid[5];
    double fractional_epoch_control_grid[5];
    double fractional_exact_score, fractional_control_score, fractional_margin;
    double fractional_residual_cfo_hz, fractional_tracking_cfo_hz;
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
    int32_t interval_screened_cells, interval_possible_peaks;
    int32_t interval_repaired_cells, interval_scalar_fallbacks;
    double total_cpu_ms, proposal_ms, stage_sum_ms;
    double proposal_fold_ms, proposal_correlation_ms, proposal_ranking_ms;
    double coarse_ms, acquisition_ms, fine_fft_ms, conditioned_ms;
    double verification_ms, glrt_ms;
    double fractional_epoch_ms;
    leo_native_glrt_candidate candidates[LEO_NATIVE_GLRT_MAX_CANDIDATES];
} leo_native_glrt_row;

typedef struct {
    size_t row_count;
    double detector_cpu_ms;
    leo_native_glrt_row rows[LEO_NATIVE_GLRT_MAX_ROWS];
} leo_native_glrt_result;

typedef struct {
    double allocation_cpu_ms, allocation_wall_ms;
    double preparation_cpu_ms, preparation_wall_ms;
    double proposals_cpu_ms, proposals_wall_ms;
    double search_cpu_ms, search_wall_ms;
    double cleanup_cpu_ms, cleanup_wall_ms;
    size_t prepared_complex_times;
} leo_native_glrt_profile;

enum {
    LEO_NATIVE_GLRT_OK = 0,
    LEO_NATIVE_GLRT_INVALID = -1,
    LEO_NATIVE_GLRT_NOMEM = -2,
    LEO_NATIVE_GLRT_BUSY = -3,
    LEO_NATIVE_GLRT_KERNEL = -4
};

enum {
    LEO_NATIVE_GLRT_CFO_REFINEMENT_SKIPPED = 0,
    LEO_NATIVE_GLRT_CFO_REFINEMENT_COMPLETE = 1
};

enum {
    LEO_NATIVE_GLRT_MODE_ORDINARY = 0,
    /* Preserves ordinary fields and adds the retained five-cell epoch lane. */
    LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH = 1,
    /* Separate slow coverage experiment: retain all eight native hypotheses,
     * run full conditioned acquisition, then fractional epoch confirmation. */
    LEO_NATIVE_GLRT_MODE_SERVER_COVERAGE_FRACTIONAL = 2,
    /* Portable server-reference translation: full FP64 anchor grid, deployed
     * basin separation, full fine/conditioned CFO, fractional confirmation. */
    LEO_NATIVE_GLRT_MODE_SERVER_REFERENCE_FRACTIONAL = 3,
    /* Deployed adaptive wrapper semantics around the reference kernel:
     * per-visit geometry, 5-sample/10 kHz basin retention, and a peer-triggered
     * retry with the 22-symbol adaptive anchor set. */
    LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_WRAPPER_FRACTIONAL = 4,
    /* Same wrapper contract with a certified FP32 interval screen and exact
     * FP64 repair; ambiguous numerical frontiers retain scalar fallback. */
    LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL = 5
};

typedef struct {
    uint32_t abi_version;
    uint32_t receiver_count;
    uint32_t probe_ms;
    uint32_t process_serialized;
    uint32_t candidate_cfo_refinement_state_available;
    uint32_t fractional_epoch_mode_available;
    uint32_t server_reference_fractional_mode_available;
    uint32_t deployed_server_wrapper_fractional_mode_available;
    uint32_t deployed_server_interval_fractional_mode_available;
    uint32_t fractional_epoch_server_parity_qualified;
} leo_native_glrt_capabilities;

/* The frozen Wave8 kernels contain process-global FFT caches. Create, analyze,
 * and destroy calls are process-serialized; concurrent calls return BUSY. */
int leo_native_glrt_create(leo_native_glrt **out, uint32_t sample_rate_hz,
    const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template, size_t template_complex_count);
int leo_native_glrt_create_with_mode(leo_native_glrt **out, uint32_t sample_rate_hz,
    const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template, size_t template_complex_count,
    uint32_t mode);
/* Configure the immutable search geometry consumed by the reference mode.
 * Centers are absolute baseband Hz for receiver 0/1; residual bounds match
 * SymbolwiseAcquisitionConfig and are shared by the receiver pair. */
int leo_native_glrt_set_server_reference_geometry(leo_native_glrt *context,
    const double receiver_center_hz[2], double residual_cfo_min_hz,
    double residual_cfo_max_hz);
int leo_native_glrt_destroy(leo_native_glrt *context);
int leo_native_glrt_layout(uint32_t sample_rate_hz, uint32_t dwell_ms,
    uint32_t probe_stride_ms, size_t *complex_times, size_t *row_count);
int leo_native_glrt_analyze(leo_native_glrt *context,
    const int16_t *dual_rx_iqiq, size_t complex_times,
    uint32_t dwell_ms, uint32_t probe_stride_ms,
    leo_native_glrt_result *result);
/* Like leo_native_glrt_analyze, with disjoint outer-stage CPU and monotonic-wall
 * measurements. The profile is committed only with a successful result. */
int leo_native_glrt_analyze_profiled(leo_native_glrt *context,
    const int16_t *dual_rx_iqiq, size_t complex_times,
    uint32_t dwell_ms, uint32_t probe_stride_ms,
    leo_native_glrt_result *result, leo_native_glrt_profile *profile);
/* Static process capabilities. The returned structure has no borrowed data. */
int leo_native_glrt_get_capabilities(leo_native_glrt_capabilities *out);
/* Never infer fractional availability from a numerical zero. */
int leo_native_glrt_candidate_cfo_refinement_state(
    const leo_native_glrt_candidate *candidate);
const char *leo_native_glrt_status_string(int status);

#endif
