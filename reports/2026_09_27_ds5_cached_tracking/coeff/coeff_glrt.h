#ifndef LEO_RESEARCH_COEFF_GLRT_H
#define LEO_RESEARCH_COEFF_GLRT_H

#include "known_state_v2.h"

#define LEO_COEFF_SYMBOLS 64

typedef struct leo_coeff_workspace leo_coeff_workspace;
typedef struct {
    leo_known_state_v2_result score;
    uint32_t coefficient_tables_built, coefficient_table_hits;
    double coefficient_build_cpu_ms, coefficient_dot_cpu_ms;
    double correlation_max_abs_error, correlation_max_relative_error;
    double ceiling_max_abs_error, ceiling_max_relative_error;
    double baseline_exact_score, baseline_control_score, baseline_cfo_residual_hz;
    uint32_t baseline_peak_bin, coefficient_peak_bin;
} leo_coeff_result;

leo_coeff_workspace *leo_coeff_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count);
void leo_coeff_destroy(leo_coeff_workspace *workspace);
/* Full-aperture final GLRT only. Integer-offset calls use the unchanged GLRT.
 * Fractional calls transpose the 16-tap interpolation into pilot coefficients.
 * Caller IQ uses the same selected-RX stride contract as known-state V2. */
int leo_coeff_measure_ci16(leo_coeff_workspace *workspace,
    const int16_t *receiver_iq, size_t sample_count, uint32_t sample_stride_i16,
    double epoch_samples, double scored_cfo_hz, leo_coeff_result *result);

#endif
