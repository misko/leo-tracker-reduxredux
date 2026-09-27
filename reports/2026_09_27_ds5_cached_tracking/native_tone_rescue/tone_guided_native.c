/* Research-only fixed-point scorer with the stable blind nuisance transform. */
#include "../native_guided_boundary/guided_boundary_native.c"
#include "tone_guided_native.h"

#if !LEO_PRESENCE_TONE_NUISANCE || !LEO_PRESENCE_TONE_CI16 || !LEO_PRESENCE_TONE_BLOCKED
#error "tone-guided scoring requires the qualified blind nuisance profile"
#endif

leo_tone_guided_workspace *leo_tone_guided_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t bins)
{
    return leo_tg11_create(rate,exact,control,n,bins);
}

void leo_tone_guided_destroy(leo_tone_guided_workspace *w)
{
    leo_tg11_destroy(w);
}

double leo_tone_guided_support_guard_hz(void)
{
    return GUIDED_CFO_SUPPORT_GUARD_HZ;
}

int leo_tone_guided_probe_ci16(leo_tone_guided_workspace *w,
    const int16_t *raw, size_t count, uint32_t receiver, uint32_t probe,
    int32_t epoch, double fractional, double scored_cfo,
    double expected_physical_cfo, leo_tone_guided_result *out)
{
    if (!w || !w->v4 || !raw || !out || count!=w->dwell_samples || receiver>1 ||
        probe>=LEO_TG11_PROBES || epoch<0 ||
        (size_t)epoch>=w->v4->dwell->confirm->n ||
        !isfinite(fractional) || fabs(fractional)>2 || !isfinite(scored_cfo) ||
        fabs(scored_cfo)>400000 || !isfinite(expected_physical_cfo) ||
        fabs(expected_physical_cfo-scored_cfo)>
            GUIDED_CFO_RESIDUAL_SUPPORT_HZ+GUIDED_CFO_SUPPORT_GUARD_HZ ||
        fegetround()!=FE_TONEAREST) return -1;

    leo_tone_guided_result result={0};
    result.schema_version=1;
    result.probe_index=probe;
    result.epoch=epoch;
    result.fractional_offset_samples=fractional;
    result.scored_cfo_hz=scored_cfo;
    result.expected_physical_cfo_hz=expected_physical_cfo;
    result.valid_bounds=1;
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    double wall=clock_ms(CLOCK_MONOTONIC);

    const int16_t *source=probe_rx(w,raw,receiver,probe);
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (size_t k=0; k<w->v4->window; ++k) {
        w->v4->selected[2*k]=source[4*k];
        w->v4->selected[2*k+1]=source[4*k+1];
    }
    result.pack_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    leo_presence_workspace *presence=w->v4->dwell->confirm;
    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (size_t k=0; k<w->v4->window; ++k)
        presence->samples[k]=w->v4->selected[2*k]+I*(double)w->v4->selected[2*k+1];
    result.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    memset(&presence->profile,0,sizeof(presence->profile));
    memset(&presence->nuisance,0,sizeof(presence->nuisance));
    presence->nuisance.enabled=1;
    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if (tone_nuisance(presence,w->v4->window,w->v4->selected)) return -1;
    result.nuisance_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    presence->nuisance.cpu_ms=result.nuisance_cpu_ms;
    result.nuisance=presence->nuisance;

    double scores[3]={0};
    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if (glrt(presence,w->v4->window,epoch,scored_cfo,fractional,16,1,scores))
        return -1;
    result.glrt_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    result.glrt_evaluations=1;
    result.fractional_complete=1;
    result.support_frames=(uint32_t)final_support_frames(
        presence,w->v4->window,epoch,fractional);
    result.valid_support=result.support_frames>=2;
    result.exact_score=scores[0];
    result.control_score=scores[1];
    result.margin=scores[0]-scores[1];
    result.cfo_residual_from_scored_hz=scores[2];
    result.tracking_cfo_hz=scored_cfo+scores[2];
    result.physical_cfo_innovation_hz=
        result.tracking_cfo_hz-expected_physical_cfo;
    if (fabs(result.physical_cfo_innovation_hz)>KNOWN_CFO_TRUST_HZ)
        result.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;
    result.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}
