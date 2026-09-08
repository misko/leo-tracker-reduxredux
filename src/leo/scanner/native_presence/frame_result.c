#include "frame_result.h"
#include <math.h>

int leo_glrt_unavailable_record(const leo_probe_request *q, enum leo_glrt_reason reason,
    leo_glrt_classification_v1 *output)
{
    if (!q || !output || reason<=LEO_GLRT_COMPLETE || reason>LEO_GLRT_CANCELLED) return -1;
    if (!q->session || !q->generation || (q->rate_hz!=2500000 && q->rate_hz!=5000000) ||
        q->rx>1 || q->channel<1 || q->channel>4 || q->edge>1 ||
        q->probe_start!=q->valid_start || q->valid_end<=q->valid_start ||
        q->sample_count!=q->rate_hz/50*6 || q->valid_end-q->valid_start!=q->sample_count) return -1;
    leo_glrt_classification_v1 r={
        .sequence=q->sequence,.visit=q->visit,.valid_start=q->valid_start,.valid_end=q->valid_end,
        .search_start=q->valid_start,.search_end=q->valid_start,
        .confirmation_start=q->valid_start,.confirmation_end=q->valid_start,
        .rate_hz=q->rate_hz,.channel=(uint8_t)q->channel,.edge=(uint8_t)q->edge,.rx=(uint8_t)q->rx,
        .verdict=LEO_GLRT_UNAVAILABLE,.reason=(uint32_t)reason,
    };
    if (leo_glrt_record_validate(&r)) return -1;
    *output=r;
    return 0;
}

int leo_glrt_result_record(const leo_probe_result *in, const leo_glrt_decision_policy *policy,
    leo_glrt_classification_v1 *output)
{
    if (!in || !output || (in->status!=0 && in->status!=-1)) return -1;
    const leo_probe_request *q=&in->request;
    if (policy && (!isfinite(policy->minimum_exact_score) || policy->minimum_exact_score<0 ||
        !isfinite(policy->minimum_margin) || policy->minimum_margin<=0 ||
        policy->classification_enabled>1 || policy->absence_enabled>1 ||
        policy->absence_enabled>policy->classification_enabled)) return -1;
    leo_glrt_classification_v1 r;
    if (leo_glrt_unavailable_record(q,LEO_GLRT_WORKER_FAILED,&r)) return -1;
    if (!in->status) {
        const leo_probe_dwell_evidence *d=&in->dwell;
        uint32_t window=d->rank.order[0];
        if (d->search_window_mask!=63 || window>=6 || d->confirmation_window_mask!=(1u<<window) ||
            in->evidence.candidate_count<0 || in->evidence.candidate_count>2 ||
            !isfinite(d->total_cpu_ms) || !isfinite(d->total_wall_ms) ||
            d->total_cpu_ms<0 || d->total_wall_ms<0) return -1;
        r.search_end=q->valid_end; r.search_window_mask=d->search_window_mask;
        r.cpu_ms=d->total_cpu_ms; r.wall_ms=d->total_wall_ms;
        r.reason=LEO_GLRT_UNQUALIFIED_CLASSIFIER;
        const leo_presence_candidate *best=NULL;
        int positive=0, incomplete=0;
        for (int j=0;j<in->evidence.candidate_count;++j) {
            const leo_presence_candidate *c=&in->evidence.candidates[j];
            if (c->fractional_complete!=0 && c->fractional_complete!=1) return -1;
            if (!c->fractional_complete) { incomplete=1; continue; }
            /* Validate every considered candidate, not only the eventual best.
             * Absolute time uses integer addition; never cast the device epoch
             * to double. Fractional offset remains a separate measurement. */
            leo_glrt_classification_v1 candidate=r;
            candidate.confirmation_start=q->valid_start+(uint64_t)window*(q->rate_hz/50);
            candidate.confirmation_end=candidate.confirmation_start+q->rate_hz/50;
            if (c->epoch<0 || (uint32_t)c->epoch>=q->rate_hz/50) return -1;
            candidate.epoch_sample_counter=candidate.confirmation_start+(uint32_t)c->epoch;
            candidate.fractional_offset_samples=c->fractional_offset_samples;
            candidate.exact_score=c->exact_score; candidate.control_score=c->control_score;
            candidate.margin=c->margin; candidate.cfo_hz=c->tracking_cfo_hz;
            if (leo_glrt_record_validate(&candidate)) return -1;
            int passes=policy && policy->classification_enabled &&
                c->exact_score>=policy->minimum_exact_score && c->margin>=policy->minimum_margin;
            if (!best || passes>positive || (passes==positive && c->margin>best->margin)) {
                best=c; positive=passes; r=candidate;
            }
        }
        if (policy && policy->classification_enabled) {
            if (positive) { r.verdict=LEO_GLRT_STARLINK; r.reason=LEO_GLRT_COMPLETE; }
            else if (policy->absence_enabled && !incomplete) {
                r.verdict=LEO_GLRT_NO_SIGNAL; r.reason=LEO_GLRT_COMPLETE;
            } else r.reason=LEO_GLRT_INCOMPLETE_SEARCH;
        }
    }
    if (leo_glrt_record_validate(&r)) return -1;
    *output=r;
    return 0;
}
