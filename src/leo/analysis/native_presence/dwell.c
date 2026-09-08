#define _POSIX_C_SOURCE 200809L
#include "dwell.h"
#include <stdlib.h>
#include <time.h>

struct leo_presence_dwell_workspace {
    uint32_t rate;
    leo_presence_rank_workspace *rank, *timing;
    leo_presence_workspace *confirm;
};

static double dwell_clock(clockid_t id)
{
    struct timespec ts;
    if (clock_gettime(id,&ts)) return 0;
    return ts.tv_sec*1000.0+ts.tv_nsec/1e6;
}

void leo_presence_dwell_destroy(leo_presence_dwell_workspace *w)
{
    if (!w) return;
    leo_presence_rank_destroy(w->rank);
    leo_presence_rank_destroy(w->timing);
    leo_presence_destroy(w->confirm);
    free(w);
}

leo_presence_dwell_workspace *leo_presence_dwell_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t bins)
{
    leo_presence_dwell_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->rate=rate;
    w->rank=leo_presence_rank_create(rate,exact,n,bins);
    if (w->rank) w->confirm=leo_presence_create(rate,exact,control,n);
    if (!w->rank || !w->confirm) { leo_presence_dwell_destroy(w); return NULL; }
    return w;
}

leo_presence_dwell_workspace *leo_presence_dwell_create_multires(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t screen_bins, uint32_t timing_bins)
{
    leo_presence_dwell_workspace *w=leo_presence_dwell_create(rate,exact,control,n,screen_bins);
    if (!w) return NULL;
    w->timing=leo_presence_rank_create(rate,exact,n,timing_bins);
    if (!w->timing) { leo_presence_dwell_destroy(w); return NULL; }
    return w;
}

int leo_presence_dwell_run_ci16(leo_presence_dwell_workspace *w, const int16_t *iq,
    size_t count, uint32_t maximum, uint32_t seeded, leo_presence_dwell_result *out)
{
    if (!w || !iq || !out || count!=w->rate/50*6 || !maximum || maximum>6 || seeded>1) return -1;
    leo_presence_dwell_result result={0};
    double cpu=dwell_clock(CLOCK_PROCESS_CPUTIME_ID), wall=dwell_clock(CLOCK_MONOTONIC);
    if (leo_presence_rank_ci16(w->rank,iq,count,&result.rank)) return -1;
    size_t window=w->rate/50;
    for (uint32_t k=0; k<maximum; ++k) {
        uint32_t index=result.rank.order[k];
        const int16_t *samples=iq+2*index*window;
        uint32_t epoch=result.rank.projected_epoch_samples[index];
        if (seeded && w->timing) {
            if (leo_presence_rank_window_ci16(w->timing,samples,window,&result.timing_proposals[k])) return -1;
            epoch=result.timing_proposals[k].epoch;
        }
        int status=seeded ? leo_presence_confirm_ci16(w->confirm,samples,window,
            (int32_t)epoch,&result.confirmations[k]) :
            leo_presence_run_ci16(w->confirm,samples,window,&result.confirmations[k]);
        if (status || leo_presence_get_nuisance(w->confirm,&result.nuisances[k])) return -1;
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
