#ifndef LEO_RESEARCH_KNOWN_STATE_H
#define LEO_RESEARCH_KNOWN_STATE_H

#include <stddef.h>
#include <stdint.h>
#include "presence.h"

enum {
    LEO_KNOWN_STATE_FAST_POINT = 0,
    LEO_KNOWN_STATE_LOCAL_TIMING = 1
};

enum {
    LEO_KNOWN_STATE_EVALUATED = 0,
    LEO_KNOWN_STATE_TIMING_REACQUIRE = 1,
    LEO_KNOWN_STATE_CFO_REACQUIRE = 2
};

typedef struct {
    uint32_t schema_version;
    uint32_t mode;
    uint32_t status;
    uint32_t scored_fractional;
    uint32_t timing_search_performed;
    uint32_t timing_bracketed;
    uint32_t support_frames;
    uint32_t glrt_evaluations;
    uint32_t valid_bounds;
    int32_t epoch;
    double fractional_offset_samples;
    double predicted_epoch_samples;
    double predicted_cfo_hz;
    double scored_cfo_hz;
    double tracking_cfo_hz;
    double cfo_innovation_hz;
    double exact_score;
    double control_score;
    double margin;
    double conversion_cpu_ms;
    double kernel_cpu_ms;
    double total_cpu_ms;
    double total_wall_ms;
} leo_known_state_result;

/* Research-only known-state final GLRT. This is not blind acquisition.
 * The input is exactly one selected 20 ms CI16 interval. FAST_POINT scores the
 * caller's fractional timing/CFO once. LOCAL_TIMING adds a +/-1-sample bracket
 * and log-parabolic timing interpolation. Both retain full-aperture final
 * exact/rolled-control GLRT scoring and report fresh CFO innovation. */
leo_presence_workspace *leo_known_state_create(uint32_t rate_hz,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count);
void leo_known_state_destroy(leo_presence_workspace *workspace);
int leo_known_state_measure_ci16(leo_presence_workspace *workspace,
    const int16_t *interleaved_iq, size_t sample_count,
    double predicted_epoch_samples, double predicted_cfo_hz, uint32_t mode,
    leo_known_state_result *result);

#endif
