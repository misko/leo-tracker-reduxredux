/* V2 layers strided/selective CI16 ingestion on the stable V1 research port.
 * V1 is included unchanged so both artifacts use the identical deployment
 * final-GLRT kernel and physical-period normalization. */
#include "known_state.c"
#include "known_state_v2.h"

static uint32_t convert_glrt_support(leo_presence_workspace *w, const int16_t *iq,
    size_t count, uint32_t stride, int epoch, double offset, int frame_limit)
{
    uint32_t converted=0;
    int integer=fabs(offset-nearbyint(offset))<=1e-12;
    for (int frame=0; frame<frame_limit; ++frame) {
        int start=frame_start(w,epoch,frame);
        int first_symbol=LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY && (frame&1) ? 152 : 2;
        int first=symbol_start(w,first_symbol);
        int stop=symbol_start(w,first_symbol+64);
        if (first_symbol!=2 && start+stop-1+offset >= (int)count-(integer ? 0 : 8)) {
            first=symbol_start(w,2);
            stop=symbol_start(w,66);
        }
        if (start+stop-1+offset >= (double)count-(integer ? 0 : 8)) break;
        if (start+first+offset < (integer ? 0 : 7)) break;
        int lower, upper;
        if (integer) {
            int shift=(int)nearbyint(offset);
            lower=start+first+shift;
            upper=start+stop+shift;
        } else {
            int shift=(int)floor(offset);
            lower=start+first+shift-7;
            upper=start+stop+shift+8;
        }
        if (lower<0) lower=0;
        if (upper>(int)count) upper=(int)count;
        for (int k=lower; k<upper; ++k)
            w->samples[k]=iq[stride*(size_t)k]+I*(double)iq[stride*(size_t)k+1];
        converted+=(uint32_t)(upper-lower);
    }
    return converted;
}

static int v2_glrt(leo_presence_workspace *w, const int16_t *iq, size_t count,
    uint32_t stride, int epoch, double cfo, double offset, int frame_limit,
    double score[3], uint32_t *converted, double *conversion_cpu_ms)
{
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    *converted+=convert_glrt_support(w,iq,count,stride,epoch,offset,frame_limit);
    *conversion_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    return glrt(w,count,epoch,cfo,offset,frame_limit,1,score);
}

int leo_known_state_v2_measure_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, uint32_t stride, double predicted_epoch, double predicted_cfo,
    uint32_t recover, uint32_t frame_limit, leo_known_state_v2_result *out)
{
    if (!w || !iq || !out || count!=w->max_samples || stride<2 || stride>16 ||
        !isfinite(predicted_epoch) || !isfinite(predicted_cfo) ||
        fabs(predicted_cfo)>400000 || recover>1 ||
        (frame_limit!=2 && frame_limit!=4 && frame_limit!=16) ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_known_state_v2_result result={0};
    result.schema_version=1;
    result.mode=recover;
    result.predicted_epoch_samples=predicted_epoch;
    result.predicted_cfo_hz=predicted_cfo;
    result.scored_cfo_hz=predicted_cfo;
    result.valid_bounds=1;
    result.sample_stride_i16=stride;
    result.frame_limit=frame_limit;
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    double wall=clock_ms(CLOCK_MONOTONIC);
    int epoch=0;
    double fractional=0;
    normalize_phase(w,predicted_epoch,&epoch,&fractional);
    double score[3]={0};
    if (v2_glrt(w,iq,count,stride,epoch,predicted_cfo,fractional,frame_limit,
        score,&result.converted_samples,&result.conversion_cpu_ms)) return -1;
    result.glrt_evaluations=1;
    if (recover) {
        result.timing_search_performed=1;
        result.timing_bracketed=1;
        double grid[3][3]={{0}};
        memcpy(grid[1],score,sizeof(score));
        for (int cell=0; cell<3; cell+=2) {
            int local=0;
            double local_fractional=0;
            normalize_phase(w,predicted_epoch+cell-1,&local,&local_fractional);
            if (v2_glrt(w,iq,count,stride,local,predicted_cfo,local_fractional,
                frame_limit,grid[cell],&result.converted_samples,
                &result.conversion_cpu_ms)) return -1;
            ++result.glrt_evaluations;
        }
        int best=0;
        for (int k=1; k<3; ++k) if (grid[k][0]>grid[best][0]) best=k;
        if (best!=1) {
            result.timing_bracketed=0;
            normalize_phase(w,predicted_epoch+best-1,&epoch,&fractional);
            memcpy(score,grid[best],sizeof(score));
        } else {
            double a=log(fmax(grid[0][0],DBL_MIN));
            double b=log(fmax(grid[1][0],DBL_MIN));
            double d=log(fmax(grid[2][0],DBL_MIN));
            double curve=a-2*b+d;
            double correction=0;
            if (isfinite(curve) && curve < -DBL_EPSILON)
                correction=fmax(-0.5,fmin(0.5,0.5*(a-d)/curve));
            normalize_phase(w,predicted_epoch+correction,&epoch,&fractional);
            if (v2_glrt(w,iq,count,stride,epoch,predicted_cfo,fractional,
                frame_limit,score,&result.converted_samples,
                &result.conversion_cpu_ms)) return -1;
            ++result.glrt_evaluations;
        }
    }
    result.epoch=epoch;
    result.fractional_offset_samples=fractional;
    result.scored_fractional=1;
    result.available_support_frames=(uint32_t)final_support_frames(w,count,epoch,fractional);
    result.support_frames=result.available_support_frames;
    if (result.support_frames>frame_limit) result.support_frames=frame_limit;
    result.exact_score=score[0];
    result.control_score=score[1];
    result.margin=score[0]-score[1];
    result.cfo_innovation_hz=score[2];
    result.tracking_cfo_hz=predicted_cfo+score[2];
    if (recover && !result.timing_bracketed) result.status|=LEO_KNOWN_STATE_TIMING_REACQUIRE;
    if (fabs(score[2])>KNOWN_CFO_TRUST_HZ || fabs(result.tracking_cfo_hz)>400000)
        result.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;
    result.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.kernel_cpu_ms=result.total_cpu_ms-result.conversion_cpu_ms;
    result.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}
