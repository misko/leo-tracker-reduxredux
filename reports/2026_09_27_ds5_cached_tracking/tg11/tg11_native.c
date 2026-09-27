/* Research-only TG11 observation engine. The included V4 source exposes its
 * exact natural-stride rank fold and stable presence workspaces in this TU. */
#include "../native/blind_strided_v4.c"
#include "tg11_native.h"

struct leo_tg11_workspace {
    leo_blind_strided_v4_workspace *v4;
    uint32_t rate;
    size_t dwell_samples, half_window;
};

static const int16_t *probe_rx(const leo_tg11_workspace *w, const int16_t *raw,
    uint32_t receiver, uint32_t probe)
{
    return raw+4*(size_t)probe*w->half_window+2*receiver;
}

leo_tg11_workspace *leo_tg11_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t n, uint32_t bins)
{
    if ((rate!=2500000 && rate!=5000000) || !exact || !control) return NULL;
    leo_tg11_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->rate=rate;
    w->dwell_samples=(size_t)rate*120/1000;
    w->half_window=rate/100;
    w->v4=leo_blind_strided_v4_create(rate,exact,control,n,bins,0);
    if (!w->v4) { free(w); return NULL; }
    return w;
}

void leo_tg11_destroy(leo_tg11_workspace *w)
{
    if (!w) return;
    leo_blind_strided_v4_destroy(w->v4);
    free(w);
}

int leo_tg11_screen_ci16(leo_tg11_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, leo_tg11_screen_result *out)
{
    if (!w || !w->v4 || !raw || !out || count!=w->dwell_samples || receiver>1 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_tg11_screen_result result={0};
    result.probe_count=LEO_TG11_PROBES;
    double cpu=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
    double wall=rank_clock(CLOCK_MONOTONIC);
    leo_presence_rank_workspace *rank=w->v4->dwell->rank;
    rank->have_screens=0;
    for (uint32_t probe=0; probe<LEO_TG11_PROBES; ++probe) {
        result.probe_start_samples[probe]=(uint32_t)((size_t)probe*w->half_window);
        const int16_t *samples=probe_rx(w,raw,receiver,probe);
        double started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        v4_fold(rank,samples,4);
        result.fold_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
        started=rank_clock(CLOCK_PROCESS_CPUTIME_ID);
        for (uint32_t projection=0; projection<PROJECTION_COUNT; ++projection) {
            leo_presence_timing_proposal timing={0};
            if (correlate(rank,projection,&timing)) return -1;
            result.projection_scores[projection][probe]=timing.score;
            result.projection_epochs[projection][probe]=timing.epoch;
        }
        result.correlation_cpu_ms+=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-started;
    }
    for (uint32_t projection=0; projection<PROJECTION_COUNT; ++projection) {
        double first=-1, second=-1;
        for (uint32_t probe=0; probe<LEO_TG11_PROBES; ++probe) {
            double score=result.projection_scores[projection][probe];
            if (score>first) { second=first; first=score; }
            else if (score>second) second=score;
        }
        result.projection_contrast[projection]=first/fmax(second,1e-30);
    }
    result.selected_projection=LEO_PRESENCE_RANK_AREA_PROJECTION;
    if (LEO_PRESENCE_RANK_HYBRID_PROJECTION &&
        result.projection_contrast[1]>result.projection_contrast[0])
        result.selected_projection=1;
    for (uint32_t probe=0; probe<LEO_TG11_PROBES; ++probe) {
        uint32_t row=result.selected_projection;
        result.scores[probe]=result.projection_scores[row][probe];
        result.projected_epoch_samples[probe]=result.projection_epochs[row][probe];
    }
    result.total_cpu_ms=rank_clock(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=rank_clock(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}

static void blind_observation(leo_presence_workspace *confirm,
    const leo_presence_candidate *candidate, uint32_t probe, uint32_t index,
    size_t window, double cpu, double wall, leo_tg11_observation *out)
{
    leo_tg11_observation result={0};
    result.probe_index=probe;
    result.candidate_index=index;
    result.fitted=1;
    result.fractional_complete=(uint32_t)candidate->fractional_complete;
    result.epoch=candidate->epoch;
    result.fractional_offset_samples=candidate->fractional_offset_samples;
    result.acquired_cfo_hz=candidate->acquired_cfo_hz;
    result.tracking_cfo_hz=candidate->tracking_cfo_hz;
    result.exact_score=candidate->exact_score;
    result.control_score=candidate->control_score;
    result.margin=candidate->margin;
    result.valid_bounds=1;
    result.support_frames=(uint32_t)final_support_frames(confirm,window,
        candidate->epoch,candidate->fractional_offset_samples);
    /* This 20 ms aperture normally contains only 14--15 usable 750 Hz
     * frames. The preregistered research support gate is at least two actual
     * frames; fractional completion remains a separate requirement. */
    result.valid_support=result.support_frames>=2;
    result.total_cpu_ms=cpu;
    result.total_wall_ms=wall;
    *out=result;
}

int leo_tg11_blind_probe_ci16(leo_tg11_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, uint32_t probe,
    leo_tg11_observation observations[2], uint32_t *observation_count)
{
    if (!w || !w->v4 || !raw || !observations || !observation_count ||
        count!=w->dwell_samples || receiver>1 || probe>=LEO_TG11_PROBES ||
        fegetround()!=FE_TONEAREST) return -1;
    const int16_t *samples=probe_rx(w,raw,receiver,probe);
    for (size_t k=0; k<w->v4->window; ++k) {
        w->v4->selected[2*k]=samples[4*k];
        w->v4->selected[2*k+1]=samples[4*k+1];
    }
    leo_presence_result native={0};
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    double wall=clock_ms(CLOCK_MONOTONIC);
    if (leo_presence_run_ci16(w->v4->dwell->confirm,w->v4->selected,
        w->v4->window,&native)) return -1;
    double cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    double wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    if (native.candidate_count<0 || native.candidate_count>2) return -1;
    for (int32_t k=0; k<native.candidate_count; ++k)
        blind_observation(w->v4->dwell->confirm,&native.candidates[k],probe,
            (uint32_t)k,w->v4->window,cpu_ms,wall_ms,&observations[k]);
    *observation_count=(uint32_t)native.candidate_count;
    return 0;
}

int leo_tg11_guided_probe_ci16(leo_tg11_workspace *w, const int16_t *raw,
    size_t count, uint32_t receiver, uint32_t probe, double epoch,
    double scored_cfo, double expected_physical_cfo, leo_tg11_observation *out)
{
    if (!w || !w->v4 || !raw || !out || count!=w->dwell_samples || receiver>1 ||
        probe>=LEO_TG11_PROBES) return -1;
    leo_known_state_v3_result native={0};
    if (leo_known_state_v3_measure_ci16(w->v4->dwell->confirm,
        probe_rx(w,raw,receiver,probe),w->v4->window,4,epoch,scored_cfo,
        expected_physical_cfo,0,16,&native)) return -1;
    leo_tg11_observation result={0};
    result.probe_index=probe;
    result.fitted=0;
    result.fractional_complete=native.score.scored_fractional;
    result.valid_bounds=native.score.valid_bounds;
    result.status=native.score.status;
    result.epoch=native.score.epoch;
    result.fractional_offset_samples=native.score.fractional_offset_samples;
    result.acquired_cfo_hz=native.score.scored_cfo_hz;
    result.tracking_cfo_hz=native.score.tracking_cfo_hz;
    result.exact_score=native.score.exact_score;
    result.control_score=native.score.control_score;
    result.margin=native.score.margin;
    result.support_frames=native.score.support_frames;
    result.valid_support=native.score.valid_bounds && native.score.support_frames>=2;
    result.total_cpu_ms=native.score.total_cpu_ms;
    result.total_wall_ms=native.score.total_wall_ms;
    *out=result;
    return 0;
}
