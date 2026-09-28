/* Research extension compiled with a hash-pinned deployment presence.c.
 * Including the implementation in this translation unit lets this bounded
 * port ingest CI16 once and invoke the unchanged final GLRT kernel directly.
 * It is deliberately not a production dependency or public persisted ABI. */
#include "presence.c"
#include "known_state.h"

#include <float.h>

#define KNOWN_CFO_TRUST_HZ 8000.0

static void normalize_phase(const leo_presence_workspace *w, double phase,
    int *epoch, double *fractional)
{
    const double period=w->rate/750.0;
    phase=fmod(phase,period);
    if (phase<0) phase+=period;
    long center=lround(phase);
    *fractional=phase-center;
    /* The physical 750 Hz period is fractional at both supported rates.
     * Template length is rounded (3333/6667); a phase near the upper boundary
     * must be represented as epoch zero with a small negative offset, never by
     * taking modulo the rounded template length. */
    if (center>=(long)w->n) {
        center=0;
        *fractional=phase-period;
    }
    *epoch=(int)center;
}

static int final_support_frames(const leo_presence_workspace *w, size_t count,
    int epoch, double offset)
{
    int frames=0;
    int integer=fabs(offset-nearbyint(offset))<=1e-12;
    for (int frame=0; frame<16; ++frame) {
        int start=frame_start(w,epoch,frame);
        int first_symbol=LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY && (frame&1) ? 152 : 2;
        int first=symbol_start(w,first_symbol);
        int stop=symbol_start(w,first_symbol+64);
        if (first_symbol!=2 && start+stop-1+offset >= (int)count-(integer ? 0 : 8)) {
            first_symbol=2;
            first=symbol_start(w,2);
            stop=symbol_start(w,66);
        }
        if (start+stop-1+offset >= (double)count-(integer ? 0 : 8)) break;
        if (start+first+offset < (integer ? 0 : 7)) break;
        ++frames;
    }
    return frames;
}

leo_presence_workspace *leo_known_state_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control, size_t n)
{
    return leo_presence_create(rate,exact,control,n);
}

void leo_known_state_destroy(leo_presence_workspace *w)
{
    leo_presence_destroy(w);
}

int leo_known_state_measure_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, double predicted_epoch, double predicted_cfo, uint32_t mode,
    leo_known_state_result *out)
{
    if (!w || !iq || !out || count!=w->max_samples ||
        !isfinite(predicted_epoch) || !isfinite(predicted_cfo) ||
        fabs(predicted_cfo)>400000 || mode>LEO_KNOWN_STATE_LOCAL_TIMING ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_known_state_result result={0};
    result.schema_version=2;
    result.mode=mode;
    result.predicted_epoch_samples=predicted_epoch;
    result.predicted_cfo_hz=predicted_cfo;
    result.scored_cfo_hz=predicted_cfo;
    result.valid_bounds=1;
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    double wall=clock_ms(CLOCK_MONOTONIC);
    for (size_t k=0; k<count; ++k) w->samples[k]=iq[2*k]+I*(double)iq[2*k+1];
    result.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    double kernel=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    int epoch=0;
    double fractional=0;
    normalize_phase(w,predicted_epoch,&epoch,&fractional);
    double scores[3]={0};
    if (glrt(w,count,epoch,predicted_cfo,fractional,16,1,scores)) return -1;
    result.glrt_evaluations=1;
    if (mode==LEO_KNOWN_STATE_LOCAL_TIMING) {
        result.timing_search_performed=1;
        result.timing_bracketed=1;
        double grid_scores[3]={0};
        double grid_control[3]={0};
        double grid_residual[3]={0};
        grid_scores[1]=scores[0];
        grid_control[1]=scores[1];
        grid_residual[1]=scores[2];
        for (int cell=0; cell<3; cell+=2) {
            int delta=cell-1;
            int local=0;
            double local_fractional=0;
            normalize_phase(w,predicted_epoch+delta,&local,&local_fractional);
            double value[3]={0};
            if (glrt(w,count,local,predicted_cfo,local_fractional,16,1,value)) return -1;
            grid_scores[cell]=value[0];
            grid_control[cell]=value[1];
            grid_residual[cell]=value[2];
            ++result.glrt_evaluations;
        }
        int best=0;
        for (int k=1; k<3; ++k) if (grid_scores[k]>grid_scores[best]) best=k;
        if (best!=1) {
            result.timing_bracketed=0;
            normalize_phase(w,predicted_epoch+best-1,&epoch,&fractional);
            scores[0]=grid_scores[best];
            scores[1]=grid_control[best];
            scores[2]=grid_residual[best];
        } else {
            double a=log(fmax(grid_scores[0],DBL_MIN));
            double b=log(fmax(grid_scores[1],DBL_MIN));
            double d=log(fmax(grid_scores[2],DBL_MIN));
            double curve=a-2*b+d;
            double correction=0;
            if (isfinite(curve) && curve < -DBL_EPSILON)
                correction=fmax(-0.5,fmin(0.5,0.5*(a-d)/curve));
            normalize_phase(w,predicted_epoch+correction,&epoch,&fractional);
            if (glrt(w,count,epoch,predicted_cfo,fractional,16,1,scores)) return -1;
            ++result.glrt_evaluations;
        }
    }
    result.epoch=epoch;
    result.fractional_offset_samples=fractional;
    result.scored_fractional=1;
    result.support_frames=(uint32_t)final_support_frames(w,count,epoch,fractional);
    result.exact_score=scores[0];
    result.control_score=scores[1];
    result.margin=scores[0]-scores[1];
    result.cfo_innovation_hz=scores[2];
    result.tracking_cfo_hz=predicted_cfo+scores[2];
    if (result.timing_search_performed && !result.timing_bracketed)
        result.status|=LEO_KNOWN_STATE_TIMING_REACQUIRE;
    if (fabs(scores[2])>KNOWN_CFO_TRUST_HZ || fabs(result.tracking_cfo_hz)>400000)
        result.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;
    result.kernel_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-kernel;
    result.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}
