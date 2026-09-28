#define _POSIX_C_SOURCE 200809L
#include <stdint.h>

#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_RANK_FORCE_SCALAR)
#include <arm_neon.h>
static inline void v5_neon_fold_group(const int16_t *a_iq, const int16_t *b_iq,
    uint32_t receiver, int64_t *sum_real, int64_t *sum_imag)
{
    int16x4x4_t a=vld4_s16(a_iq), b=vld4_s16(b_iq);
    int16x4_t ar=receiver ? a.val[2] : a.val[0];
    int16x4_t ai=receiver ? a.val[3] : a.val[1];
    int16x4_t br=receiver ? b.val[2] : b.val[0];
    int16x4_t bi=receiver ? b.val[3] : b.val[1];
    int32x4_t rr=vmull_s16(ar,br), ii=vmull_s16(ai,bi);
    int32x4_t ri=vmull_s16(ar,bi), ir=vmull_s16(ai,br);
    int64x2_t re0=vaddq_s64(vmovl_s32(vget_low_s32(rr)),vmovl_s32(vget_low_s32(ii)));
    int64x2_t re1=vaddq_s64(vmovl_s32(vget_high_s32(rr)),vmovl_s32(vget_high_s32(ii)));
    int64x2_t im0=vsubq_s64(vmovl_s32(vget_low_s32(ri)),vmovl_s32(vget_low_s32(ir)));
    int64x2_t im1=vsubq_s64(vmovl_s32(vget_high_s32(ri)),vmovl_s32(vget_high_s32(ir)));
    vst1q_s64(sum_real,vaddq_s64(vld1q_s64(sum_real),re0));
    vst1q_s64(sum_real+2,vaddq_s64(vld1q_s64(sum_real+2),re1));
    vst1q_s64(sum_imag,vaddq_s64(vld1q_s64(sum_imag),im0));
    vst1q_s64(sum_imag+2,vaddq_s64(vld1q_s64(sum_imag+2),im1));
}
#endif

#ifdef LEO_V5_NEON_PROBE_ONLY
#if !defined(__ARM_NEON) || defined(LEO_PRESENCE_RANK_FORCE_SCALAR)
#error "V5 NEON probe requires the ARM NEON path"
#endif
/* External wrapper makes the exact production helper visible in disassembly. */
void leo_v5_neon_probe(const int16_t *a_iq, const int16_t *b_iq,
    uint32_t receiver, int64_t *sum_real, int64_t *sum_imag)
{
    v5_neon_fold_group(a_iq,b_iq,receiver,sum_real,sum_imag);
}
#else

/* Separate V5 artifact; V4 and all known-state artifacts remain frozen. */
#include "blind_strided_v4.c"
#include "blind_aligned_v5.h"

static void v5_fold(leo_presence_rank_workspace *w, const int16_t *raw,
    uint32_t receiver)
{
#if !RANK_FULL_FOLD
    size_t group_cursor=0;
#endif
    for (size_t block=0; block<w->n; block+=256) {
        size_t end=block+256<w->n ? block+256 : w->n;
#if !RANK_FULL_FOLD
        size_t first_group=group_cursor;
        while (group_cursor<w->group_count && w->groups[group_cursor]<end) ++group_cursor;
#endif
        memset(w->sum_real+block,0,(end-block)*sizeof(*w->sum_real));
        memset(w->sum_imag+block,0,(end-block)*sizeof(*w->sum_imag));
        for (size_t frame=0; frame<15; ++frame) {
            size_t start=w->starts[frame], valid=w->window-start-4;
            if (valid>end) valid=end;
#if RANK_FULL_FOLD
            size_t k=block, stop=valid;
#else
            for (size_t group=first_group; group<group_cursor; ++group) {
                size_t k=w->groups[group];
                size_t stop=k+4<valid ? k+4 : valid;
#endif
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_RANK_FORCE_SCALAR)
#if RANK_FULL_FOLD
            for (; k+3<valid; k+=4) {
#else
            if (k+3<valid) {
#endif
                /* Both loads begin at RX0 I on a real sample boundary. The
                 * second consumes samples k+4..k+7; the fold validity rule
                 * proves k+7 is inside this 20 ms interval. */
                v5_neon_fold_group(raw+4*(start+k),raw+4*(start+k+4),receiver,
                    w->sum_real+k,w->sum_imag+k);
#if !RANK_FULL_FOLD
                k+=4;
#endif
            }
#endif
            for (; k<stop; ++k) {
                size_t offset=4*(start+k)+2*receiver;
                int64_t ar=raw[offset], ai=raw[offset+1];
                int64_t br=raw[offset+16], bi=raw[offset+17];
                w->sum_real[k]+=ar*br+ai*bi;
                w->sum_imag[k]+=ar*bi-ai*br;
            }
#if !RANK_FULL_FOLD
            }
#endif
        }
    }
    for (size_t k=0; k<w->n; ++k) {
        if (!w->needed[k]) continue;
        double support=w->support[k] ? w->support[k] : 1;
        w->folded[k]=(double)w->sum_real[k]/support+I*((double)w->sum_imag[k]/support);
    }
}

static int v5_rank_window(leo_presence_rank_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, leo_presence_timing_proposal *result)
{
    if (w) w->have_screens=0;
    if (!w || !raw || !result || count!=w->window || receiver>1 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_timing_proposal out={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    v5_fold(w,raw,receiver);
    out.fold_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    if (correlate(w,0,&out)) return -1;
    out.correlation_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}

static int v5_rank(leo_presence_rank_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, leo_presence_rank_result *result)
{
    if (w) w->have_screens=0;
    if (!w || !raw || !result || count!=6*w->window || receiver>1 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_rank_result out={0};
    leo_presence_rank_screens screens={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    for (size_t slice=0; slice<6; ++slice) {
        double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        v5_fold(w,raw+4*slice*w->window,receiver);
        out.fold_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
        started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        for (size_t projection=0; projection<PROJECTION_COUNT; ++projection) {
            size_t row=LEO_PRESENCE_RANK_AREA_PROJECTION+projection;
            leo_presence_timing_proposal timing={0};
            if (correlate(w,projection,&timing)) return -1;
            screens.available_mask|=1u<<row;
            screens.scores[row][slice]=timing.score;
            screens.epochs[row][slice]=timing.epoch;
            uint32_t *order=screens.order[row];
            order[slice]=(uint32_t)slice;
            for (size_t j=slice; j>0 && screens.scores[row][order[j]]>
                screens.scores[row][order[j-1]]; --j) {
                uint32_t swap=order[j]; order[j]=order[j-1]; order[j-1]=swap;
            }
        }
        out.correlation_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    }
    screens.selected=LEO_PRESENCE_RANK_AREA_PROJECTION;
    for (size_t row=0; row<2; ++row) if (screens.available_mask&(1u<<row))
        screens.contrast[row]=screens.scores[row][screens.order[row][0]] /
            fmax(screens.scores[row][screens.order[row][1]],1e-30);
    if (LEO_PRESENCE_RANK_HYBRID_PROJECTION && screens.contrast[1]>screens.contrast[0])
        screens.selected=1;
    memcpy(out.scores,screens.scores[screens.selected],sizeof(out.scores));
    memcpy(out.order,screens.order[screens.selected],sizeof(out.order));
    memcpy(out.projected_epoch_samples,screens.epochs[screens.selected],
        sizeof(out.projected_epoch_samples));
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    w->screens=screens;
    w->have_screens=1;
    return 0;
}

leo_blind_aligned_v5_workspace *leo_blind_aligned_v5_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t screen_bins, uint32_t timing_bins)
{
    return leo_blind_strided_v4_create(rate,exact,control,n,screen_bins,timing_bins);
}

void leo_blind_aligned_v5_destroy(leo_blind_aligned_v5_workspace *w)
{
    leo_blind_strided_v4_destroy(w);
}

int leo_blind_aligned_v5_run_ci16(leo_blind_aligned_v5_workspace *w,
    const int16_t *raw, size_t count, uint32_t receiver, uint32_t maximum,
    uint32_t seeded, leo_presence_dwell_result *out)
{
    if (!w || !w->dwell || !raw || !out || count!=6*w->window || receiver>1 ||
        !maximum || maximum>6 || seeded>1) return -1;
    leo_presence_dwell_result result={0};
    double cpu=dwell_clock(CLOCK_PROCESS_CPUTIME_ID), wall=dwell_clock(CLOCK_MONOTONIC);
    if (v5_rank(w->dwell->rank,raw,count,receiver,&result.rank)) return -1;
    for (uint32_t k=0; k<maximum; ++k) {
        uint32_t index=result.rank.order[k];
        const int16_t *samples=raw+4*index*w->window;
        uint32_t epoch=result.rank.projected_epoch_samples[index];
        if (seeded && w->dwell->timing) {
            if (v5_rank_window(w->dwell->timing,samples,w->window,receiver,
                &result.timing_proposals[k])) return -1;
            epoch=result.timing_proposals[k].epoch;
        }
        for (size_t sample=0; sample<w->window; ++sample) {
            w->selected[2*sample]=samples[4*sample+2*receiver];
            w->selected[2*sample+1]=samples[4*sample+2*receiver+1];
        }
        int status=seeded ? leo_presence_confirm_ci16(w->dwell->confirm,w->selected,
            w->window,(int32_t)epoch,&result.confirmations[k]) :
            leo_presence_run_ci16(w->dwell->confirm,w->selected,w->window,
                &result.confirmations[k]);
        if (status || leo_presence_get_nuisance(w->dwell->confirm,
            &result.nuisances[k])) return -1;
        result.confirmation_window_mask|=1u<<index;
        ++result.confirmation_count;
        result.prefix_cpu_ms[k]=dwell_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        result.prefix_wall_ms[k]=dwell_clock(CLOCK_MONOTONIC)-wall;
    }
    result.total_cpu_ms=dwell_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=dwell_clock(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}

int leo_blind_aligned_v5_get_screens(const leo_blind_aligned_v5_workspace *w,
    leo_presence_rank_screens *screens)
{
    return leo_blind_strided_v4_get_screens(w,screens);
}

int leo_blind_aligned_v5_get_profile(const leo_blind_aligned_v5_workspace *w,
    leo_presence_profile *profile)
{
    return w && w->dwell ? leo_presence_get_profile(w->dwell->confirm,profile) : -1;
}

#endif
