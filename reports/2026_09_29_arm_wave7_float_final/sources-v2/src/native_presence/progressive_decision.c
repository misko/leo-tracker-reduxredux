#define _POSIX_C_SOURCE 200809L
#include "progressive_decision.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

struct leo_progressive_workspace {
    leo_presence_workspace *presence;
    float taps[129];
    int16_t *filtered;
};

static double now(clockid_t id)
{ struct timespec t; clock_gettime(id,&t); return t.tv_sec*1000.0+t.tv_nsec/1e6; }
static int16_t quantize(float x)
{ float y=nearbyintf(x); return y>32767 ? 32767 : y< -32768 ? -32768 : (int16_t)y; }

int leo_progressive_filter(const int16_t *iq, size_t count, unsigned window,
    const float taps[129], int16_t *out)
{
    if (!iq || !taps || !out || count!=1200000 || window>=6) return -1;
    for (unsigned k=0;k<129;++k) if (!isfinite(taps[k])) return -1;
    size_t base=(size_t)window*200000;
    for (size_t m=0;m<100000;++m) {
        int64_t first=(int64_t)base+2*(int64_t)m-128;
        float re=0,im=0;
        unsigned k=0;
#if defined(__ARM_NEON)
        if (first>=0) {
            float32x4_t ar=vdupq_n_f32(0),ai=vdupq_n_f32(0);
            for (;k<128;k+=4) {
                int16x4x2_t x=vld2_s16(iq+2*((size_t)first+k));
                float32x4_t h=vld1q_f32(taps+k);
                ar=vmlaq_f32(ar,vcvtq_f32_s32(vmovl_s16(x.val[0])),h);
                ai=vmlaq_f32(ai,vcvtq_f32_s32(vmovl_s16(x.val[1])),h);
            }
            float32x2_t rr=vadd_f32(vget_low_f32(ar),vget_high_f32(ar));
            float32x2_t ii=vadd_f32(vget_low_f32(ai),vget_high_f32(ai));
            float32x2_t pair=vpadd_f32(rr,ii);
            int16x4_t last=vld1_s16(iq+2*((size_t)first+128));
            pair=vmla_n_f32(pair,vget_low_f32(vcvtq_f32_s32(vmovl_s16(last))),taps[128]);
            pair=vmin_f32(vmax_f32(pair,vdup_n_f32(-32768)),vdup_n_f32(32767));
            /* Bounded FP32 round-to-nearest-even without a libm/fenv call
             * for every component. All values remain in the unit-ULP binade
             * around 1.5*2^23. No fast-math reassociation is enabled. */
            float32x2_t magic=vdup_n_f32(12582912.0f);
            pair=vsub_f32(vadd_f32(pair,magic),magic);
            int32x2_t integer=vcvt_s32_f32(pair);
            int16x4_t narrow=vmovn_s32(vcombine_s32(integer,integer));
            out[2*m]=vget_lane_s16(narrow,0); out[2*m+1]=vget_lane_s16(narrow,1);
            continue;
        }
#endif
        for (;k<129;++k) if (first+(int64_t)k>=0) {
            size_t p=2*(size_t)(first+k);
            re+=iq[p]*taps[k]; im+=iq[p+1]*taps[k];
        }
        out[2*m]=quantize(re); out[2*m+1]=quantize(im);
    }
    return 0;
}

leo_progressive_workspace *leo_progressive_create(const leo_presence_complex *exact,
    const leo_presence_complex *control, size_t count, const float taps[129])
{
    if (!taps) return NULL;
    for (unsigned k=0;k<129;++k) if (!isfinite(taps[k])) return NULL;
    leo_progressive_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->presence=leo_presence_create(5000000,exact,control,count);
    w->filtered=calloc(200000,sizeof(int16_t));
    memcpy(w->taps,taps,sizeof(w->taps));
    if (!w->presence || !w->filtered) { leo_progressive_destroy(w); return NULL; }
    return w;
}

void leo_progressive_destroy(leo_progressive_workspace *w)
{ if (w) { leo_presence_destroy(w->presence); free(w->filtered); free(w); } }

int leo_progressive_run(leo_progressive_workspace *w, const int16_t *iq,
    size_t count, double budget_ms, leo_progressive_result *out)
{
    if (!w || !iq || !out || count!=1200000 || !isfinite(budget_ms) || budget_ms<0)
        return -1;
    const unsigned order[6]={0,2,4,1,3,5};
    leo_progressive_result r={0};
    double start=now(CLOCK_PROCESS_CPUTIME_ID), wall=now(CLOCK_MONOTONIC);
    for (unsigned j=0;j<6;++j) {
        unsigned window=order[j];
        double before=now(CLOCK_PROCESS_CPUTIME_ID);
        if (budget_ms && before-start>=budget_ms) { r.budget_exceeded=1; break; }
        if (leo_progressive_filter(iq,count,window,w->taps,w->filtered)) return -1;
        double filtered=now(CLOCK_PROCESS_CPUTIME_ID);
        leo_presence_result *c=&r.confirmations[window];
        if (leo_presence_run_ci16(w->presence,w->filtered,100000,c)) return -1;
        double after=now(CLOCK_PROCESS_CPUTIME_ID);
        r.filter_cpu_ms+=filtered-before; r.confirm_cpu_ms+=after-filtered;
        r.probe_cpu_ms[window]=after-before;
        ++r.probes; r.mask|=1u<<window;
        for (int k=0;k<c->candidate_count;++k)
            if (c->candidates[k].fractional_complete && c->candidates[k].exact_score>=0.175 &&
                c->candidates[k].margin>=0.025) r.positive_mask|=1u<<window;
        if (budget_ms && after-start>budget_ms) { r.budget_exceeded=1; break; }
        if (r.positive_mask) { r.outcome=1; break; }
        if (r.mask==63) r.outcome=2;
    }
    r.total_cpu_ms=now(CLOCK_PROCESS_CPUTIME_ID)-start;
    r.total_wall_ms=now(CLOCK_MONOTONIC)-wall;
    *out=r;
    return 0;
}
