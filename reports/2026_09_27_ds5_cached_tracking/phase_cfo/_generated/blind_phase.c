/* Separate V4 artifact: stable V1/V2/V3 sources and binaries remain intact. */
#include "presence.c"
#include "window_rank.c"
#include "dwell.c"
#include "blind_strided_v4.h"

struct leo_blind_strided_v4_workspace {
    leo_presence_dwell_workspace *dwell;
    int16_t *selected;
    size_t window;
};

static void v4_fold(leo_presence_rank_workspace *w, const int16_t *iq,
    uint32_t stride)
{
    if (stride==2) { fold(w,iq); return; }
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
            /* The natural stride-4 recording layout is scalar here. A vld4
             * load based at RX1 consumes two int16 values from the following
             * raw sample and can cross the terminal source bound. Retain safe
             * exact loads until a future ABI supplies raw base plus RX index. */
            for (; k<stop; ++k) {
                size_t offset=stride*(start+k);
                int64_t ar=iq[offset], ai=iq[offset+1];
                int64_t br=iq[offset+4*stride], bi=iq[offset+4*stride+1];
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

static int v4_rank_window(leo_presence_rank_workspace *w, const int16_t *iq,
    size_t count, uint32_t stride, leo_presence_timing_proposal *result)
{
    if (w) w->have_screens=0;
    if (!w || !iq || !result || count!=w->window || stride<2 || stride>16 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_timing_proposal out={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    v4_fold(w,iq,stride);
    out.fold_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    if (correlate(w,0,&out)) return -1;
    out.correlation_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    out.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}

static int v4_rank(leo_presence_rank_workspace *w, const int16_t *iq,
    size_t count, uint32_t stride, leo_presence_rank_result *result)
{
    if (w) w->have_screens=0;
    if (!w || !iq || !result || count!=6*w->window || stride<2 || stride>16 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_presence_rank_result out={0};
    leo_presence_rank_screens screens={0};
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID), wall=rank_clock(CLOCK_MONOTONIC);
    for (size_t slice=0; slice<6; ++slice) {
        double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        v4_fold(w,iq+stride*slice*w->window,stride);
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

leo_blind_strided_v4_workspace *leo_blind_strided_v4_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t screen_bins, uint32_t timing_bins)
{
    leo_blind_strided_v4_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->window=rate/50;
    w->dwell=timing_bins ? leo_presence_dwell_create_multires(rate,exact,control,n,
        screen_bins,timing_bins) : leo_presence_dwell_create(rate,exact,control,n,screen_bins);
    w->selected=calloc(2*w->window,sizeof(*w->selected));
    if (!w->dwell || !w->selected) { leo_blind_strided_v4_destroy(w); return NULL; }
    return w;
}

void leo_blind_strided_v4_destroy(leo_blind_strided_v4_workspace *w)
{
    if (!w) return;
    leo_presence_dwell_destroy(w->dwell);
    free(w->selected);
    free(w);
}

int leo_blind_strided_v4_run_ci16(leo_blind_strided_v4_workspace *w,
    const int16_t *iq, size_t count, uint32_t stride, uint32_t maximum,
    uint32_t seeded, leo_presence_dwell_result *out)
{
    if (!w || !w->dwell || !iq || !out || count!=6*w->window || stride<2 ||
        stride>16 || !maximum || maximum>6 || seeded>1) return -1;
    leo_presence_dwell_result result={0};
    double cpu=dwell_clock(CLOCK_PROCESS_CPUTIME_ID), wall=dwell_clock(CLOCK_MONOTONIC);
    if (v4_rank(w->dwell->rank,iq,count,stride,&result.rank)) return -1;
    for (uint32_t k=0; k<maximum; ++k) {
        uint32_t index=result.rank.order[k];
        const int16_t *samples=iq+stride*index*w->window;
        uint32_t epoch=result.rank.projected_epoch_samples[index];
        if (seeded && w->dwell->timing) {
            if (v4_rank_window(w->dwell->timing,samples,w->window,stride,
                &result.timing_proposals[k])) return -1;
            epoch=result.timing_proposals[k].epoch;
        }
        for (size_t sample=0; sample<w->window; ++sample) {
            w->selected[2*sample]=samples[stride*sample];
            w->selected[2*sample+1]=samples[stride*sample+1];
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

int leo_blind_strided_v4_get_screens(const leo_blind_strided_v4_workspace *w,
    leo_presence_rank_screens *screens)
{
    return w && w->dwell ? leo_presence_rank_get_screens(w->dwell->rank,screens) : -1;
}


int leo_phase_cfo_get_profile(const leo_blind_strided_v4_workspace *w,
    leo_presence_profile *profile)
{
    return w && w->dwell ? leo_presence_get_profile(w->dwell->confirm,profile) : -1;
}
