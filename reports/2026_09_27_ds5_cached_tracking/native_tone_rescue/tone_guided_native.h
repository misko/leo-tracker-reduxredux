#ifndef LEO_RESEARCH_TONE_GUIDED_NATIVE_H
#define LEO_RESEARCH_TONE_GUIDED_NATIVE_H

#include <stddef.h>
#include <stdint.h>
#include "../tg11/tg11_native.h"

typedef leo_tg11_workspace leo_tone_guided_workspace;

typedef struct {
    uint32_t schema_version;
    uint32_t probe_index, support_frames, valid_support;
    uint32_t fractional_complete, valid_bounds, status, glrt_evaluations;
    uint32_t coarse_search_evaluations, fine_search_evaluations;
    uint32_t conditioned_search_evaluations, epoch_lattice_evaluations;
    int32_t epoch;
    double fractional_offset_samples;
    double scored_cfo_hz, expected_physical_cfo_hz;
    double cfo_residual_from_scored_hz, tracking_cfo_hz;
    double physical_cfo_innovation_hz;
    double exact_score, control_score, margin;
    leo_presence_nuisance nuisance;
    double pack_cpu_ms, conversion_cpu_ms, nuisance_cpu_ms, glrt_cpu_ms;
    double total_cpu_ms, total_wall_ms;
} leo_tone_guided_result;

leo_tone_guided_workspace *leo_tone_guided_create(uint32_t rate_hz,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count, uint32_t screen_bins);

void leo_tone_guided_destroy(leo_tone_guided_workspace *workspace);

/* One rescue-only fixed point. Input is a complete natural
 * [sample][receiver][I,Q] 120 ms CI16 dwell. The supplied integer/fractional
 * timing components are kept separate so blind-candidate parity can preserve
 * its exact floating-point representation. Caller IQ is never modified. */
int leo_tone_guided_probe_ci16(leo_tone_guided_workspace *workspace,
    const int16_t *raw, size_t dwell_sample_count, uint32_t receiver,
    uint32_t probe_index, int32_t epoch, double fractional_offset_samples,
    double scored_cfo_hz, double expected_physical_cfo_hz,
    leo_tone_guided_result *result);

double leo_tone_guided_support_guard_hz(void);

#endif
