#ifndef LEO_RESEARCH_TG11_NATIVE_H
#define LEO_RESEARCH_TG11_NATIVE_H

#include <stddef.h>
#include <stdint.h>
#include "presence.h"

#define LEO_TG11_PROBES 11

typedef struct leo_tg11_workspace leo_tg11_workspace;

typedef struct {
    uint32_t probe_count, selected_projection;
    uint32_t probe_start_samples[LEO_TG11_PROBES];
    uint32_t projected_epoch_samples[LEO_TG11_PROBES];
    double scores[LEO_TG11_PROBES];
    double projection_scores[2][LEO_TG11_PROBES];
    uint32_t projection_epochs[2][LEO_TG11_PROBES];
    double projection_contrast[2];
    double fold_cpu_ms, correlation_cpu_ms, total_cpu_ms, total_wall_ms;
} leo_tg11_screen_result;

typedef struct {
    uint32_t probe_index, candidate_index, support_frames, valid_support;
    uint32_t fitted, fractional_complete, valid_bounds, status;
    int32_t epoch;
    double fractional_offset_samples;
    double acquired_cfo_hz, tracking_cfo_hz;
    double exact_score, control_score, margin;
    double total_cpu_ms, total_wall_ms;
} leo_tg11_observation;

leo_tg11_workspace *leo_tg11_create(uint32_t rate_hz,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins);
void leo_tg11_destroy(leo_tg11_workspace *workspace);

/* Input is the complete natural [sample][receiver][I,Q] 120 ms CI16 layout.
 * receiver selects lane 0 or 1. Each 20 ms probe is screened exactly once. */
int leo_tg11_screen_ci16(leo_tg11_workspace *workspace, const int16_t *raw,
    size_t sample_count, uint32_t receiver, leo_tg11_screen_result *result);

/* Confirm one already-screened probe without repeating any rank operation.
 * The two native unseeded candidates are returned in their native order. */
int leo_tg11_blind_probe_ci16(leo_tg11_workspace *workspace, const int16_t *raw,
    size_t sample_count, uint32_t receiver, uint32_t probe_index,
    leo_tg11_observation observations[2], uint32_t *observation_count);

/* Full-aperture predicted-and-verified measurement. Scoring and expected
 * physical CFO are separate causal inputs. No timing fit is performed. */
int leo_tg11_guided_probe_ci16(leo_tg11_workspace *workspace, const int16_t *raw,
    size_t sample_count, uint32_t receiver, uint32_t probe_index,
    double predicted_epoch_samples, double scored_cfo_hz,
    double expected_physical_cfo_hz, leo_tg11_observation *observation);

#endif
