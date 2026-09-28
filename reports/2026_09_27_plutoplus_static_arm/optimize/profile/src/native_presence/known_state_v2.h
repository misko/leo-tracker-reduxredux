#ifndef LEO_RESEARCH_KNOWN_STATE_V2_H
#define LEO_RESEARCH_KNOWN_STATE_V2_H

#include <stddef.h>
#include <stdint.h>
#include "presence.h"

typedef struct {
    uint32_t schema_version, mode, status, scored_fractional;
    uint32_t timing_search_performed, timing_bracketed;
    uint32_t support_frames, available_support_frames, frame_limit;
    uint32_t glrt_evaluations, valid_bounds, sample_stride_i16, converted_samples;
    int32_t epoch;
    double fractional_offset_samples, predicted_epoch_samples, predicted_cfo_hz;
    double scored_cfo_hz, tracking_cfo_hz, cfo_innovation_hz;
    double exact_score, control_score, margin;
    double conversion_cpu_ms, kernel_cpu_ms, total_cpu_ms, total_wall_ms;
} leo_known_state_v2_result;

/* Strided research port. sample_stride_i16 is the distance between adjacent
 * complex samples (2 for packed single RX, 4 for one RX view of dual-RX IQ).
 * frame_limit=16 preserves full final-GLRT aperture; 2/4 are explicitly
 * partial-support proposals with distinct, unqualified score semantics. */
int leo_known_state_v2_measure_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t sample_count, uint32_t sample_stride_i16,
    double predicted_epoch_samples, double predicted_cfo_hz,
    uint32_t recover_timing, uint32_t frame_limit,
    leo_known_state_v2_result *result);

#endif
