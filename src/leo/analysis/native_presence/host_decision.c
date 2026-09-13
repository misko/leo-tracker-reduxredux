#define _POSIX_C_SOURCE 200809L
#include "host_decision.h"
#include "decision_decimator.h"
#include "dwell.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "host_decision_coefficients.inc"

struct leo_host_decision {
    leo_decimator *filter;
    leo_presence_dwell_workspace *dwell[2];
    int16_t *filtered;
};

static double host_clock(clockid_t id)
{
    struct timespec t;
    if (clock_gettime(id, &t)) return 0;
    return t.tv_sec*1000.0+t.tv_nsec/1e6;
}

void leo_host_decision_destroy_v1(leo_host_decision *w)
{
    if (!w) return;
    leo_decimator_destroy(w->filter);
    for (unsigned i=0; i<2; ++i) leo_presence_dwell_destroy(w->dwell[i]);
    free(w->filtered);
    free(w);
}

leo_host_decision *leo_host_decision_create_v1(const leo_presence_complex *t, size_t n)
{
    if (!t || n!=3333) return NULL;
    leo_host_decision *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->filtered=malloc(300000*2*sizeof(*w->filtered));
    w->filter=leo_decimator_create(NULL,0,host_decision_coefficients,161,1200000);
    for (unsigned i=0; i<2; ++i)
        w->dwell[i]=leo_presence_dwell_create(2500000,t+2*i*n,t+(2*i+1)*n,n,512);
    if (!w->filtered || !w->filter || !w->dwell[0] || !w->dwell[1]) {
        leo_host_decision_destroy_v1(w);
        return NULL;
    }
    return w;
}

int leo_host_decision_supported_v1(uint32_t window, int32_t epoch)
{
    if (window>=6 || epoch<0 || epoch>=3333) return 0;
    return window!=0 || epoch>=42;
}

int leo_host_decision_run_v1(leo_host_decision *w, const int16_t *iq,
    size_t count, uint32_t edge, leo_host_decision_result_v1 *out)
{
    if (!w || !iq || !out || count!=1200000 || edge>1) return -1;
    double cpu=host_clock(CLOCK_THREAD_CPUTIME_ID), wall=host_clock(CLOCK_MONOTONIC);
    if (leo_decimator_run(w->filter,iq,count,w->filtered)) return -1;
    /* Outputs 0..39 lack full support after the causal reset. Exclude their
     * observed amplitudes from ranking and confirmation; retain the support
     * boundary and reject unsupported candidate intervals explicitly. */
    memset(w->filtered,0,40*2*sizeof(*w->filtered));
    double filter_cpu=host_clock(CLOCK_THREAD_CPUTIME_ID)-cpu;
    leo_presence_dwell_result r;
    if (leo_presence_dwell_run_ci16(w->dwell[edge],w->filtered,300000,1,0,&r)) return -1;
    leo_host_decision_result_v1 result={.version=1,.screen_mask=63,
        .confirmation_mask=r.confirmation_window_mask,.supported_start=40,
        .supported_end=300000,.filter_cpu_ms=filter_cpu};
    const leo_presence_result *e=&r.confirmations[0];
    result.outcome=2;
    for (int k=0; k<e->candidate_count; ++k) {
        const leo_presence_candidate *c=&e->candidates[k];
        int supported=leo_host_decision_supported_v1(r.rank.order[0],c->epoch);
        if (!c->fractional_complete || !supported) result.outcome=0;
        if (!k) {
            result.epoch=c->epoch;
            result.fractional_complete=c->fractional_complete;
            result.candidate_supported=supported;
            result.fractional_offset=c->fractional_offset_samples;
            result.cfo_hz=c->acquired_cfo_hz;
            result.exact_score=c->exact_score;
            result.margin=c->margin;
        }
        if (supported && c->fractional_complete && c->exact_score>=.175 && c->margin>=.025) {
            result.outcome=1;
            break;
        }
    }
    memcpy(result.screen_scores,r.rank.scores,sizeof(result.screen_scores));
    result.cpu_ms=host_clock(CLOCK_THREAD_CPUTIME_ID)-cpu;
    result.wall_ms=host_clock(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}
