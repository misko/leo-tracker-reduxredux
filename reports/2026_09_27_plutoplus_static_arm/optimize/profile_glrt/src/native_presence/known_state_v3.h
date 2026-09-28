#ifndef LEO_RESEARCH_KNOWN_STATE_V3_H
#define LEO_RESEARCH_KNOWN_STATE_V3_H

#include "known_state_v2.h"

typedef struct {
    leo_known_state_v2_result score;
    double expected_physical_cfo_hz;
    double cfo_residual_from_scored_hz;
    double physical_cfo_innovation_hz;
} leo_known_state_v3_result;

/* Dual-CFO contract: scored_cfo_hz is the demodulation/acquisition center.
 * expected_physical_cfo_hz is the causal track expectation. The native GLRT
 * estimates physical CFO as scored center plus its unconstrained residual;
 * only measured-minus-expected physical innovation is checked against 8 kHz.
 * The scoring center is limited to +/-400 kHz by the inherited GLRT. Physical
 * CFO has no such absolute bound, but expected minus scored CFO must be within
 * the GLRT's +/-half-symbol-rate residual support. */
int leo_known_state_v3_measure_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t sample_count, uint32_t sample_stride_i16,
    double predicted_epoch_samples, double scored_cfo_hz,
    double expected_physical_cfo_hz, uint32_t recover_timing,
    uint32_t frame_limit, leo_known_state_v3_result *result);

#endif
