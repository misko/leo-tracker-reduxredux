/* Real SDK -> real SPSC policy -> real scheduler thread, saved IQ shadow only.
 * Hardware IO is replaced with an explicitly quantized 121ms MODEL clock and
 * zero-length mock recalls. A missed model tick FAILS; IQ is never reassigned.
 * No IIO/network/radio handles, no changes to the production components. */
#define _POSIX_C_SOURCE 200809L
#include "scanner_glrt_shadow_replay.h"
#include "spf-hop-adaptive-policy.h"
#include <errno.h>
#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <time.h>

struct choice_timing { double begin_ms,end_ms,cpu_ms; unsigned offered_before,offered_after; };
struct offer_timing { double begin_ms,end_ms; };
struct leo_replay_shadow {
    struct spf_hop_request_v2 request;
    struct spf_hop_adaptive_policy *policy;
    void *scheduler;
    const struct spf_hop_device_ops_v2 *ops;
    struct spf_hop_device_event_v2 *events;
    struct choice_timing *timing;
    struct offer_timing *offers;
    atomic_uint offered;
    uint64_t base,period;
    unsigned jobs,recalls,registered,restores;
    double origin_ms;
    int started,finished;
};

static double milliseconds(clockid_t clock)
{
    struct timespec t;
    if (clock_gettime(clock,&t)) return -1;
    return t.tv_sec*1000.0+t.tv_nsec/1e6;
}

static int mock_start(void *opaque,uint64_t lo)
{
    struct leo_replay_shadow *s=opaque;
    return lo==s->request.geometry.profiles[0].lo_frequency_hz ? 0 : -EINVAL;
}

static int mock_counter(void *opaque,uint64_t *counter)
{
    struct leo_replay_shadow *s=opaque;
    double elapsed=milliseconds(CLOCK_MONOTONIC)-s->origin_ms;
    if (elapsed<0 || elapsed>325000) return -ERANGE;
    *counter=(s->base&UINT64_C(0xffffffff))+(uint64_t)(elapsed/121)*s->period;
    return 0;
}

static int mock_recall(void *opaque,uint32_t slot,uint64_t lo,
    struct spf_hop_scheduler_transition_v1 *out)
{
    struct leo_replay_shadow *s=opaque;
    uint64_t now;
    if (mock_counter(s,&now) || s->recalls>=s->jobs || slot!=s->recalls%8 ||
        now!=(s->base&UINT64_C(0xffffffff))+(uint64_t)s->recalls*s->period ||
        lo!=s->request.geometry.profiles[slot].lo_frequency_hz) return -ERANGE;
    *out=(struct spf_hop_scheduler_transition_v1){now,now,lo,++s->recalls,slot};
    return 0;
}

static int mock_restore(void *opaque,uint64_t lo,struct spf_hop_scheduler_restore_v1 *out)
{
    struct leo_replay_shadow *s=opaque;
    uint64_t now;
    if (mock_counter(s,&now) || s->restores++) return -EINVAL;
    *out=(struct spf_hop_scheduler_restore_v1){now,now,lo,UINT32_MAX};
    return 0;
}

static int mock_sleep(void *opaque,uint64_t ns)
{
    (void)opaque;
    struct timespec t={(time_t)(ns/1000000000),(long)(ns%1000000000)};
    while (nanosleep(&t,&t)) if (errno!=EINTR) return -errno;
    return 0;
}

static int choose(void *opaque,uint64_t visit,uint64_t now,struct spf_hop_choice_v2 *out)
{
    struct leo_replay_shadow *s=opaque;
    if (visit>=s->jobs) return -ERANGE;
    struct choice_timing *t=&s->timing[visit];
    t->offered_before=atomic_load_explicit(&s->offered,memory_order_acquire);
    t->begin_ms=milliseconds(CLOCK_MONOTONIC)-s->origin_ms;
    double cpu=milliseconds(CLOCK_THREAD_CPUTIME_ID);
    int ret=spf_hop_adaptive_policy_ports()->choose(s->policy,visit,now,out);
    t->cpu_ms=milliseconds(CLOCK_THREAD_CPUTIME_ID)-cpu;
    t->end_ms=milliseconds(CLOCK_MONOTONIC)-s->origin_ms;
    t->offered_after=atomic_load_explicit(&s->offered,memory_order_acquire);
    return ret;
}

static int commit(void *opaque,const struct spf_hop_device_event_v2 *event,
    uint64_t start,uint64_t end)
{
    struct leo_replay_shadow *s=opaque;
    return spf_hop_adaptive_policy_ports()->commit(s->policy,event,start,end);
}

int leo_replay_shadow_open(struct leo_replay_shadow **out,unsigned rate,unsigned jobs,uint64_t base)
{
    if (!out || (rate!=2500000 && rate!=5000000) || !jobs || jobs>2479) return -EINVAL;
    struct leo_replay_shadow *s=calloc(1,sizeof(*s));
    if (!s) return -ENOMEM;
    s->jobs=jobs; s->base=base; s->period=(uint64_t)rate*121/1000;
    atomic_init(&s->offered,0);
    s->events=calloc(jobs,sizeof(*s->events)); s->timing=calloc(jobs,sizeof(*s->timing));
    s->offers=calloc(jobs,sizeof(*s->offers));
    if (!s->events || !s->timing || !s->offers) goto fail;
    struct spf_hop_request_v2 *r=&s->request;
    r->geometry.required_features=SPF_HOP_REQUIRED_FEATURES_V1;
    r->geometry.flags=SPF_HOP_REQUEST_FLAGS_V1;
    r->geometry.session_id=71;
    r->geometry.sample_rate_hz=r->geometry.rf_bandwidth_hz=rate;
    r->geometry.dwell_samples=(uint64_t)rate*120/1000;
    r->geometry.transition_guard_samples=rate/1000;
    r->geometry.dwell_count=2500;
    r->geometry.capture_span_samples=jobs*s->period;
    for (unsigned i=0;i<8;++i) {
        r->geometry.profiles[i].profile_id=r->geometry.profiles[i].fastlock_slot=(uint8_t)i;
        r->geometry.profiles[i].center_frequency_hz=r->geometry.profiles[i].lo_frequency_hz=1000000000+i*1000000;
        r->geometry.profiles[i].profile_crc32=100+i;
    }
    r->policy=(struct spf_hop_policy_v2){9,SPF_HOP_SHADOW,3,3,3,1,2000,3000,160,1000,3};
    static const struct spf_hop_scheduler_io_v1 io={mock_start,mock_counter,mock_recall,mock_restore,mock_sleep,NULL};
    static const struct spf_hop_scheduler_policy_v2 ports={choose,commit};
    if (spf_hop_adaptive_policy_validate_pinned(r) || spf_hop_adaptive_policy_create(&s->policy,r) ||
        spf_hop_scheduler_v2_create(r,&io,s,&ports,s,&s->scheduler,&s->ops)) goto fail;
    *out=s;
    return 0;
fail:
    leo_replay_shadow_close(s);
    return -EINVAL;
}

int leo_replay_shadow_start(struct leo_replay_shadow *s,double origin_ms)
{
    if (!s || s->started) return -EINVAL;
    s->origin_ms=origin_ms;
    int ret=s->ops->submit_plan(s->scheduler,&s->request);
    if (!ret) s->started=1;
    return ret;
}

int leo_replay_shadow_visit(struct leo_replay_shadow *s,unsigned visit,uint64_t start,
    uint64_t end,unsigned channel,unsigned edge)
{
    if (!s || visit!=s->registered || visit>=s->jobs) return -EINVAL;
    /* Bounded nonblocking drain. The 2-block delayed metadata model gives the
     * scheduler time to publish, but a missing actual receipt still fails. */
    size_t count=0;
    uint64_t dropped=0;
    if (s->ops->drain_events(s->scheduler,&s->events[visit],1,&count,&dropped) ||
        count!=1 || dropped) return -EAGAIN;
    const struct spf_hop_device_event_v2 *e=&s->events[visit];
    uint64_t offset=s->base&~UINT64_C(0xffffffff);
    if (e->device.dwell_index!=visit || e->device.to_profile!=channel-1+4*edge ||
        e->device.to_profile!=visit%8 || e->device.transition_after+offset+s->request.geometry.transition_guard_samples!=start ||
        end-start!=s->request.geometry.dwell_samples) return -EINVAL;
    ++s->registered;
    return 0;
}

int leo_replay_shadow_offer(struct leo_replay_shadow *s,const leo_adaptive_observation_v1 *o)
{
    if (!s || !o || o->visit>=s->jobs) return -EINVAL;
    struct offer_timing *t=&s->offers[o->visit];
    t->begin_ms=milliseconds(CLOCK_MONOTONIC)-s->origin_ms;
    int ret=spf_hop_adaptive_policy_offer(s->policy,o);
    if (!ret) atomic_fetch_add_explicit(&s->offered,1,memory_order_release);
    t->end_ms=milliseconds(CLOCK_MONOTONIC)-s->origin_ms;
    return ret;
}

int leo_replay_shadow_finish(struct leo_replay_shadow *s)
{
    if (!s || !s->started || s->finished) return -EINVAL;
    struct spf_hop_restore_receipt_v1 receipt;
    if (s->ops->cancel_restore(s->scheduler,SPF_HOP_REASON_CLIENT_CLOSE,&receipt)) return -EINVAL;
    s->finished=1;
    unsigned offered=atomic_load_explicit(&s->offered,memory_order_acquire);
    if (s->registered!=s->jobs || s->recalls!=s->jobs || offered!=s->jobs || s->restores!=1) return -EINVAL;
    for (unsigned i=0;i<s->jobs;++i) {
        const struct spf_hop_choice_v2 *c=&s->events[i].choice;
        const struct choice_timing *t=&s->timing[i];
        printf("{\"kind\":\"shadow-choice\",\"visit\":%u,\"actual_target\":%u,\"proposed_target\":%u,"
            "\"decision\":\"%" PRIu64 "\",\"basis_visit\":\"%" PRIu64 "\",\"active_mask\":%u,"
            "\"quiet_mask\":%u,\"reason\":%u,\"misses\":%u,\"cooldown_samples\":\"%" PRIu64 "\","
            "\"begin_ms\":%.9f,\"end_ms\":%.9f,\"cpu_ms\":%.9f,\"offered_before\":%u,\"offered_after\":%u}\n",
            i,s->events[i].device.to_profile,c->proposed_target,
            c->decision_counter+(s->base&~UINT64_C(0xffffffff)),c->basis_visit,c->active_mask,
            c->quiet_mask,c->reason,c->consecutive_misses,c->cooldown_remaining_samples,
            t->begin_ms,t->end_ms,t->cpu_ms,t->offered_before,t->offered_after);
        printf("{\"kind\":\"shadow-offer\",\"visit\":%u,\"begin_ms\":%.9f,\"end_ms\":%.9f}\n",
            i,s->offers[i].begin_ms,s->offers[i].end_ms);
    }
    struct rusage parent,worker;
    if (getrusage(RUSAGE_SELF,&parent) || getrusage(RUSAGE_CHILDREN,&worker)) return -errno;
    printf("{\"kind\":\"shadow-final\",\"choices\":%u,\"offered\":%u,\"mock_restores\":%u,"
        "\"parent_maxrss_kib\":%ld,\"worker_maxrss_kib\":%ld}\n",
        s->registered,offered,s->restores,parent.ru_maxrss,worker.ru_maxrss);
    return 0;
}

void leo_replay_shadow_close(struct leo_replay_shadow *s)
{
    if (!s) return;
    /* Join the real scheduler before releasing its policy, even on failure. */
    if (s->scheduler) spf_hop_scheduler_v2_destroy(s->scheduler);
    spf_hop_adaptive_policy_destroy(s->policy);
    free(s->events); free(s->timing); free(s->offers); free(s);
}
