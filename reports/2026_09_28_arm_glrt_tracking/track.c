#define _POSIX_C_SOURCE 200809L
#include "track.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* Deliberately share the reviewed private ingest/GLRT implementation. This
 * translation unit must not be linked with full_search.c or presence.c. */
#include "../2026_09_28_arm_full_optimization/full_search.c"

struct leo_tracking_workspace {
    uint32_t rate_hz;
    int32_t period_cells;
    leo_presence_workspace *presence;
};

static int candidate_better(const leo_tracking_candidate *a,
    const leo_tracking_candidate *b)
{
    if (a->margin != b->margin) return a->margin > b->margin;
    if (a->exact_score != b->exact_score) return a->exact_score > b->exact_score;
    int aa=abs(a->epoch_delta), ab=abs(b->epoch_delta);
    if (aa != ab) return aa < ab;
    return a->epoch < b->epoch;
}

leo_tracking_workspace *leo_tracking_create(uint32_t rate_hz,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t template_count)
{
    leo_tracking_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->presence=leo_presence_create(rate_hz,exact,control,template_count);
    if (!w->presence) { free(w); return NULL; }
    w->rate_hz=rate_hz;
    w->period_cells=(int32_t)llround((double)rate_hz/750.0);
    return w;
}

void leo_tracking_destroy(leo_tracking_workspace *w)
{
    if (w) leo_presence_destroy(w->presence);
    free(w);
}

void leo_tracking_state_reset(leo_tracking_state *state)
{
    if (state) memset(state,0,sizeof(*state));
}

int leo_tracking_state_set(leo_tracking_state *state,
    const leo_tracking_candidate *candidates, size_t count)
{
    if (!state || (count && !candidates) || count>LEO_TRACK_MAX_CANDIDATES) return -1;
    leo_tracking_state next={0};
    next.candidate_count=(int32_t)count;
    if (count) memcpy(next.candidates,candidates,count*sizeof(*candidates));
    *state=next;
    return 0;
}

int32_t leo_tracking_wrap_epoch(int32_t epoch, int32_t delta, int32_t n)
{
    if (n<=0) return -1;
    int64_t value=(int64_t)epoch+delta;
    value%=n;
    if (value<0) value+=n;
    return (int32_t)value;
}

int32_t leo_tracking_propagate_epoch(uint32_t rate_hz, int32_t epoch)
{
    double period=(double)rate_hz/750.0;
    double phase=fmod((double)epoch-(double)rate_hz/100.0,period);
    if (phase<0) phase+=period;
    int32_t n=(int32_t)llround(period);
    int32_t propagated=(int32_t)llround(phase);
    return propagated==n ? 0 : propagated;
}

static void copy_full_candidate(leo_tracking_candidate *dst,
    const leo_full_search_candidate *src, int rank)
{
    *dst=(leo_tracking_candidate){
        .seed_rank=rank, .epoch=src->candidate.epoch, .epoch_delta=0,
        .glrt_complete=src->glrt_complete, .acquisition_fields_valid=1,
        .coarse_fields_valid=1, .verification_fields_valid=1,
        .acquired_cfo_hz=src->candidate.acquired_cfo_hz,
        .tracking_cfo_hz=src->candidate.tracking_cfo_hz,
        .exact_score=src->candidate.exact_score,
        .control_score=src->candidate.control_score,
        .margin=src->candidate.margin,
    };
}

static void count_positive(leo_tracking_result *out)
{
    for (int i=0;i<out->candidate_count;++i)
        if (out->candidates[i].margin>=LEO_TRACK_POSITIVE_MARGIN) ++out->positive_count;
}

int leo_tracking_refresh(leo_tracking_workspace *w,
    const leo_presence_complex *samples, size_t count,
    leo_tracking_state *state, leo_tracking_result *result)
{
    if (!w || !state || !result) return -1;
    leo_full_search_result full;
    if (leo_full_search_run(w->presence,samples,count,&full)) return -1;
    leo_tracking_result out={0};
    out.candidate_count=full.candidate_count;
    out.candidate_eval_attempts=full.candidate_count;
    for (int i=0;i<full.candidate_count;++i)
        copy_full_candidate(&out.candidates[i],&full.candidates[i],i);
    count_positive(&out);
    out.conversion_cpu_ms=full.conversion_cpu_ms;
    out.coarse_cpu_ms=full.coarse_cpu_ms;
    out.acquisition_cpu_ms=full.acquisition_cpu_ms;
    out.fine_fft_cpu_ms=full.fine_fft_cpu_ms;
    out.conditioned_cpu_ms=full.conditioned_cpu_ms;
    out.verification_cpu_ms=full.verification_cpu_ms;
    out.glrt_cpu_ms=full.glrt_cpu_ms;
    out.total_cpu_ms=full.total_cpu_ms;
    if (leo_tracking_state_set(state,out.candidates,(size_t)out.candidate_count)) return -1;
    *result=out;
    return 0;
}

int leo_tracking_follow(leo_tracking_workspace *w,
    const leo_presence_complex *samples, size_t count,
    leo_tracking_state *state, int radius, leo_tracking_result *result)
{
    if (!w || !samples || !state || !result || (radius!=0 && radius!=1) ||
        state->candidate_count<0 || state->candidate_count>LEO_TRACK_MAX_CANDIDATES) return -1;
    leo_tracking_result out={0};
    double total_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    double stage=total_started;
    if (ingest(w->presence,samples,count)) return -1;
    out.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
    stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    out.candidate_count=state->candidate_count;
    for (int i=0;i<state->candidate_count;++i) {
        const leo_tracking_candidate *seed=&state->candidates[i];
        int32_t predicted=leo_tracking_propagate_epoch(w->rate_hz,seed->epoch);
        leo_tracking_candidate best={0};
        int have=0;
        for (int delta=-radius;delta<=radius;++delta) {
            leo_tracking_candidate candidate={
                .seed_rank=i,
                .epoch=leo_tracking_wrap_epoch(predicted,delta,w->period_cells),
                .epoch_delta=delta,
                .glrt_complete=1,
                .acquired_cfo_hz=seed->acquired_cfo_hz,
            };
            double score[3];
            ++out.candidate_eval_attempts;
            if (glrt(w->presence,count,candidate.epoch,candidate.acquired_cfo_hz,
                0,16,1,score)) return -1;
            candidate.exact_score=score[0];
            candidate.control_score=score[1];
            candidate.margin=score[0]-score[1];
            candidate.tracking_cfo_hz=candidate.acquired_cfo_hz+score[2];
            if (!have || candidate_better(&candidate,&best)) { best=candidate; have=1; }
        }
        out.candidates[i]=best;
    }
    out.glrt_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
    out.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-total_started;
    count_positive(&out);
    if (leo_tracking_state_set(state,out.candidates,(size_t)out.candidate_count)) return -1;
    *result=out;
    return 0;
}
