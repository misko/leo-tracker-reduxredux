/* Research-only numerical guard around the TG11 guided-CFO support boundary.
 * Blind acquisition and all DSP are the frozen TG11 implementation. */
#define leo_tg11_guided_probe_ci16 leo_tg11_guided_probe_ci16_original
#include "../tg11/tg11_native.c"
#undef leo_tg11_guided_probe_ci16

#include "guided_boundary_native.h"

#define GUIDED_CFO_RESIDUAL_SUPPORT_HZ (0.5/SYMBOL_S)
#define GUIDED_CFO_SUPPORT_GUARD_HZ 1e-6

double leo_tg11_guided_support_guard_hz(void)
{
    return GUIDED_CFO_SUPPORT_GUARD_HZ;
}

int leo_tg11_guided_probe_ci16(leo_tg11_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, uint32_t probe, double epoch,
    double scored_cfo, double expected_physical_cfo, leo_tg11_observation *out)
{
    if (!w || !w->v4 || !raw || !out || count!=w->dwell_samples || receiver>1 ||
        probe>=LEO_TG11_PROBES || !isfinite(expected_physical_cfo) ||
        fabs(expected_physical_cfo-scored_cfo)>
            GUIDED_CFO_RESIDUAL_SUPPORT_HZ+GUIDED_CFO_SUPPORT_GUARD_HZ)
        return -1;

    /* This is the scorer called by frozen V3. Reconstruct only V3's status
     * semantics after scoring; never clamp or modify either supplied CFO. */
    leo_known_state_v2_result native={0};
    if (leo_known_state_v2_measure_ci16(w->v4->dwell->confirm,
        probe_rx(w,raw,receiver,probe),w->v4->window,4,epoch,scored_cfo,
        0,16,&native)) return -1;
    double physical_innovation=native.tracking_cfo_hz-expected_physical_cfo;
    native.status&=~LEO_KNOWN_STATE_CFO_REACQUIRE;
    if (fabs(physical_innovation)>KNOWN_CFO_TRUST_HZ)
        native.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;

    leo_tg11_observation result={0};
    result.probe_index=probe;
    result.fitted=0;
    result.fractional_complete=native.scored_fractional;
    result.valid_bounds=native.valid_bounds;
    result.status=native.status;
    result.epoch=native.epoch;
    result.fractional_offset_samples=native.fractional_offset_samples;
    result.acquired_cfo_hz=native.scored_cfo_hz;
    result.tracking_cfo_hz=native.tracking_cfo_hz;
    result.exact_score=native.exact_score;
    result.control_score=native.control_score;
    result.margin=native.margin;
    result.support_frames=native.support_frames;
    result.valid_support=native.valid_bounds && native.support_frames>=2;
    result.total_cpu_ms=native.total_cpu_ms;
    result.total_wall_ms=native.total_wall_ms;
    *out=result;
    return 0;
}
