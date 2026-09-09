#include "adaptive_scan.h"
#include <errno.h>
#include <stdlib.h>

struct pending_visit {
    uint64_t start, end;
    uint32_t target, received, outcome, healthy;
};
struct leo_adaptive_scan {
    leo_adaptive_config_v1 config;
    leo_adaptive_target_v1 targets[LEO_ADAPTIVE_MAX_TARGETS];
    int32_t credits[LEO_ADAPTIVE_MAX_TARGETS];
    struct pending_visit *visits;
    uint64_t now, decision_counter, basis_visit;
    uint32_t committed, applied, cursor, selected, pending, fallback, unhealthy;
};

static uint64_t samples(const leo_adaptive_scan *s, uint32_t ms)
{ return (uint64_t)s->config.rate_hz * ms / 1000; }

void leo_adaptive_destroy(leo_adaptive_scan *s)
{ if (s) { free(s->visits); free(s); } }

int leo_adaptive_create(leo_adaptive_scan **out, const leo_adaptive_config_v1 *c)
{
    if (!out || !c || !c->session || !c->generation ||
        (c->rate_hz!=2500000 && c->rate_hz!=5000000) ||
        !c->target_count || c->target_count>LEO_ADAPTIVE_MAX_TARGETS ||
        !c->maximum_visits || c->maximum_visits>LEO_ADAPTIVE_MAX_VISITS ||
        !c->warmup_visits || c->warmup_visits>16 ||
        c->warmup_visits*c->target_count>c->maximum_visits ||
        !c->missed_dwells || c->missed_dwells>32 ||
        !c->quiet_weight || c->quiet_weight>c->active_weight || c->active_weight>16 ||
        !c->cooldown_ms || c->cooldown_ms>30000 ||
        c->hop_budget_ms<120 || c->hop_budget_ms>1000 ||
        c->maximum_revisit_ms<c->hop_budget_ms*c->target_count ||
        c->maximum_revisit_ms>30000 || !c->maximum_result_age_ms ||
        c->maximum_result_age_ms>10000 || !c->unhealthy_limit || c->unhealthy_limit>32)
        return -EINVAL;
    leo_adaptive_scan *s=calloc(1,sizeof(*s));
    if (!s) return -ENOMEM;
    s->visits=calloc(c->maximum_visits,sizeof(*s->visits));
    if (!s->visits) { free(s); return -ENOMEM; }
    s->config=*c; s->now=c->start_counter; s->basis_visit=LEO_ADAPTIVE_NO_VISIT;
    *out=s;
    return 0;
}

int leo_adaptive_observe(leo_adaptive_scan *s, const leo_adaptive_observation_v1 *o,
    uint64_t received)
{
    if (!s || !o || o->session!=s->config.session || o->generation!=s->config.generation ||
        o->rate_hz!=s->config.rate_hz || o->rx!=1 || o->visit>=s->committed ||
        o->outcome>LEO_ADAPTIVE_NOT_DETECTED || o->healthy>1 ||
        (!o->healthy && o->outcome!=LEO_ADAPTIVE_UNKNOWN) || received<s->now ||
        received<o->valid_end) return -EINVAL;
    struct pending_visit *v=&s->visits[o->visit];
    if (o->target!=v->target || o->valid_start!=v->start || o->valid_end!=v->end)
        return -EINVAL;
    if (o->visit<s->applied || v->received) return -EALREADY;
    /* A delayed old detection must never refresh the current cooldown. */
    int fresh=received-v->end<=samples(s,s->config.maximum_result_age_ms);
    v->received=1; v->outcome=fresh ? o->outcome : LEO_ADAPTIVE_UNKNOWN;
    v->healthy=fresh ? o->healthy : 0;
    s->now=received;
    return 0;
}

static void apply_ready(leo_adaptive_scan *s, uint64_t now)
{
    for (unsigned n=0;n<LEO_ADAPTIVE_MAX_TARGETS && s->applied<s->committed;++n) {
        struct pending_visit *v=&s->visits[s->applied];
        if (now<v->end) break;
        if (!v->received) {
            if (now-v->end<=samples(s,s->config.maximum_result_age_ms)) break;
            v->received=1; v->outcome=LEO_ADAPTIVE_UNKNOWN; v->healthy=0;
        }
        leo_adaptive_target_v1 *t=&s->targets[v->target];
        if (v->outcome==LEO_ADAPTIVE_DETECTED) {
            t->last_detection_end=v->end; t->has_detection=1;
            t->consecutive_misses=0; t->state=LEO_ADAPTIVE_ACTIVE;
        } else if (v->outcome==LEO_ADAPTIVE_NOT_DETECTED) {
            if (t->consecutive_misses<s->config.missed_dwells) ++t->consecutive_misses;
        } else t->consecutive_misses=0;
        s->unhealthy=v->healthy ? 0 : s->unhealthy+1;
        if (s->unhealthy>=s->config.unhealthy_limit) s->fallback=1;
        s->basis_visit=s->applied++;
    }
    for (uint32_t i=0;i<s->config.target_count;++i) {
        leo_adaptive_target_v1 *t=&s->targets[i];
        if (t->consecutive_misses>=s->config.missed_dwells &&
            (!t->has_detection || now-t->last_detection_end>=samples(s,s->config.cooldown_ms)))
            t->state=LEO_ADAPTIVE_QUIET;
    }
}

int leo_adaptive_choose(leo_adaptive_scan *s, uint64_t now, leo_adaptive_choice_v1 *out)
{
    if (!s || !out || now<s->now || s->committed>=s->config.maximum_visits) return -EINVAL;
    if (s->pending) return -EBUSY;
    if (s->committed && now<s->visits[s->committed-1].end) return -EINVAL;
    s->now=now;
    apply_ready(s,now);
    uint32_t count=s->config.target_count, active=0, quiet=0;
    for (uint32_t i=0;i<count;++i) {
        if (s->targets[i].state==LEO_ADAPTIVE_ACTIVE) active|=1u<<i;
        if (s->targets[i].state==LEO_ADAPTIVE_QUIET) quiet|=1u<<i;
    }
    uint32_t selected=s->cursor, reason=LEO_ADAPTIVE_WEIGHTED;
    if (s->fallback) reason=LEO_ADAPTIVE_FAULT_FALLBACK;
    else if (s->committed<s->config.warmup_visits*count) reason=LEO_ADAPTIVE_WARMUP;
    else if (!active) reason=LEO_ADAPTIVE_NONE_ACTIVE;
    if (reason!=LEO_ADAPTIVE_WEIGHTED) {
        for (uint32_t i=0;i<count;++i) s->credits[i]=0;
    } else {
        int32_t total=0;
        uint64_t oldest_age=0;
        uint32_t overdue=count;
        for (uint32_t j=0;j<count;++j) {
            uint32_t i=(s->cursor+j)%count;
            int32_t weight=(int32_t)(s->targets[i].state==LEO_ADAPTIVE_QUIET ?
                s->config.quiet_weight : s->config.active_weight);
            s->credits[i]+=weight; total+=weight;
            if (!j || s->credits[i]>s->credits[selected]) selected=i;
            uint64_t age=now-s->targets[i].last_visit_start;
            if (age>=samples(s,s->config.maximum_revisit_ms-s->config.hop_budget_ms) &&
                (overdue==count || age>oldest_age)) { overdue=i; oldest_age=age; }
        }
        if (overdue<count) { selected=overdue; reason=LEO_ADAPTIVE_EXPLORATION; }
        s->credits[selected]-=total;
        /* Debt remains bounded even under repeated deadline overrides and
         * activity changes. No unbounded catch-up burst after recovery. */
        for (uint32_t i=0;i<count;++i) {
            if (s->credits[i]>total) s->credits[i]=total;
            if (s->credits[i]<-total) s->credits[i]=-total;
        }
    }
    const leo_adaptive_target_v1 *t=&s->targets[selected];
    uint64_t remaining=0, cooldown=samples(s,s->config.cooldown_ms);
    if (t->has_detection && now-t->last_detection_end<cooldown)
        remaining=cooldown-(now-t->last_detection_end);
    *out=(leo_adaptive_choice_v1){.visit=s->committed,.decision_counter=now,
        .basis_visit=s->basis_visit,.cooldown_remaining_samples=remaining,
        .target=selected,.reason=reason,.active_mask=active,.quiet_mask=quiet,
        .consecutive_misses=t->consecutive_misses};
    s->pending=1; s->selected=selected; s->decision_counter=now;
    return 0;
}

int leo_adaptive_commit(leo_adaptive_scan *s, uint64_t start, uint64_t end)
{
    if (!s || !s->pending || start<s->now || start<s->decision_counter ||
        end<=start || end-start!=samples(s,120)) return -EINVAL;
    s->visits[s->committed++]=(struct pending_visit){.start=start,.end=end,.target=s->selected};
    leo_adaptive_target_v1 *t=&s->targets[s->selected];
    t->last_visit_start=start; ++t->visits;
    s->cursor=(s->selected+1)%s->config.target_count; s->pending=0; s->now=start;
    return 0;
}

void leo_adaptive_fallback(leo_adaptive_scan *s)
{ if (s) s->fallback=1; }

int leo_adaptive_target(const leo_adaptive_scan *s, uint32_t target, leo_adaptive_target_v1 *out)
{
    if (!s || !out || target>=s->config.target_count) return -EINVAL;
    *out=s->targets[target];
    return 0;
}
