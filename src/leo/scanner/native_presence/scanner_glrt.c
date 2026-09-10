#define _GNU_SOURCE
#include "scanner_glrt.h"
#include "frame_result.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <limits.h>
#include <math.h>

enum { PLANNED, COLLECTING, HELD, WORKING, DONE, SENT };
struct visit_record {
    leo_glrt_classification_v1 record;
    leo_adaptive_observation_v1 observation;
    uint64_t submitted_ns;
    unsigned state, skip_cause;
};
struct leo_scanner_glrt {
    leo_scanner_glrt_config_v1 config;
    leo_glrt_decision_policy policy;
    leo_probe_pool *pool;
    leo_probe_collector collector;
    struct visit_record *visits;
    int16_t *history;
    size_t history_capacity;
    uint64_t history_start, history_end, frame_sequence;
    uint32_t known, collecting, sending, observing;
    leo_scanner_glrt_protection_v1 protection;
    leo_scanner_glrt_protection_stats_v1 protection_stats;
    uint64_t now_ns;
    uint32_t oldest_pending, recovery_count;
    leo_scanner_glrt_admission_v1 admission;
    leo_scanner_glrt_admission_stats_v1 admission_stats;
    uint32_t pending_visit, pending_slot, running_visit, seen_targets, dispatched_targets;
    uint64_t pending_ns, pressure_source, last_dispatch_ns[8], last_dispatch_source[8];
    int admission_pressure;
    pid_t worker;
    int notify, have_history, finished, final, failed, cooperative_skips;
};

static void advance_admission(leo_scanner_glrt *s);

static leo_probe_request request_for(const leo_scanner_glrt *s, uint32_t index)
{
    const leo_glrt_classification_v1 *r=&s->visits[index].record;
    return (leo_probe_request){.session=s->config.session,.generation=s->config.generation,
        .sequence=index,.visit=r->visit,.valid_start=r->valid_start,.valid_end=r->valid_end,
        .probe_start=r->valid_start,.rate_hz=s->config.rate_hz,
        .sample_count=s->config.rate_hz/50*6,.rx=s->config.rx,.channel=r->channel,.edge=r->edge};
}

static void unavailable(leo_scanner_glrt *s, uint32_t index, enum leo_glrt_reason reason)
{
    leo_probe_request q=request_for(s,index);
    (void)leo_glrt_unavailable_record(&q,reason,&s->visits[index].record);
    s->visits[index].observation=(leo_adaptive_observation_v1){
        .session=q.session,.generation=q.generation,.visit=q.visit,
        .valid_start=q.valid_start,.valid_end=q.valid_end,.rate_hz=q.rate_hz,
        .rx=q.rx,.target=q.channel-1+4*q.edge,.outcome=LEO_ADAPTIVE_UNKNOWN,.healthy=0};
    s->visits[index].state=DONE;
}

/* Call only at an explicit acquisition-owner admission decision. A wire reason
 * alone is not sufficient evidence that skipping was intentional. */
static void admission_skip(leo_scanner_glrt *s, uint32_t index, enum leo_glrt_reason reason)
{
    unavailable(s,index,reason);
    if (s->cooperative_skips) {
        s->visits[index].observation.healthy=1;
        s->visits[index].skip_cause=reason==LEO_GLRT_WORKER_BUSY ?
            LEO_SCANNER_GLRT_SKIP_BACKLOG : LEO_SCANNER_GLRT_SKIP_PRESSURE;
    }
}

void leo_scanner_glrt_fail(leo_scanner_glrt *s)
{
    if (!s) return;
    s->failed=1;
    leo_probe_abort(&s->collector);
    if (s->admission_stats.enabled && s->pending_visit!=UINT32_MAX) {
        leo_probe_request q=request_for(s,s->pending_visit);
        (void)leo_probe_release_held(s->pool,s->pending_slot,&q);
        s->pending_visit=UINT32_MAX;
    }
    for (uint32_t j=s->sending;j<s->known;++j)
        if (s->visits[j].state<DONE) unavailable(s,j,LEO_GLRT_WORKER_FAILED);
    s->collecting=s->known;
    if (s->notify>=0) { close(s->notify); s->notify=-1; }
}

static void disable_worker(leo_scanner_glrt *s)
{
    leo_scanner_glrt_fail(s);
    /* Still our unreaped child; no PID lookup/reuse race, allocation or wait.
     * Subsequent harvest uses WNOHANG; close does final reaping off capture. */
    if (s->worker>0) (void)kill(s->worker,SIGKILL);
}

static void check_protection(leo_scanner_glrt *s)
{
    if (!s->protection_stats.enabled || s->failed) return;
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now)) {
        ++s->protection_stats.clock_faults; disable_worker(s); return;
    }
    uint64_t ns=(uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;
    if (ns<s->now_ns) {
        ++s->protection_stats.clock_faults; disable_worker(s); return;
    }
    s->now_ns=ns;
    while (s->oldest_pending<s->collecting && s->visits[s->oldest_pending].state>=DONE)
        ++s->oldest_pending;
    if (s->oldest_pending<s->collecting &&
        s->visits[s->oldest_pending].state==WORKING &&
        ns-s->visits[s->oldest_pending].submitted_ns>=
            (uint64_t)s->protection.worker_timeout_ms*1000000) {
        ++s->protection_stats.watchdog_trips; disable_worker(s);
    }
}

int leo_scanner_glrt_enable_protection(leo_scanner_glrt *s,
    const leo_scanner_glrt_protection_v1 *config)
{
    if (!s || !config || !config->max_occupied_slots ||
        config->max_occupied_slots>LEO_PROBE_SLOTS || !config->admission_age_ms ||
        config->admission_age_ms>=config->worker_timeout_ms ||
        config->worker_timeout_ms>1000 || !config->recovery_blocks ||
        config->recovery_blocks>1024) return -EINVAL;
    if (s->known || s->have_history || s->finished || s->failed || s->protection_stats.enabled)
        return -EBUSY;
    s->protection=*config;
    s->protection_stats.enabled=1;
    check_protection(s);
    return s->failed ? -EIO : 0;
}

int leo_scanner_glrt_enable_cooperative_skips(leo_scanner_glrt *s)
{
    if (!s) return -EINVAL;
    if (!s->policy.classification_enabled || !s->protection_stats.enabled) return -ENOTSUP;
    if (s->known || s->have_history || s->finished || s->failed || s->cooperative_skips)
        return -EBUSY;
    s->cooperative_skips=1;
    return 0;
}

int leo_scanner_glrt_enable_fair_admission(leo_scanner_glrt *s,
    const leo_scanner_glrt_admission_v1 *config)
{
    if (!s || !config || !config->maximum_pending_age_ms ||
        config->maximum_pending_age_ms>240 || config->freshness_trigger_ms<120 ||
        config->freshness_trigger_ms>10000) return -EINVAL;
    if (!s->cooperative_skips || s->protection.max_occupied_slots!=LEO_PROBE_SLOTS ||
        config->maximum_pending_age_ms>=s->protection.admission_age_ms) return -ENOTSUP;
    if (s->known || s->have_history || s->finished || s->failed || s->admission_stats.enabled)
        return -EBUSY;
    if (leo_dwell_pool_enable_held(s->pool)) return -EIO;
    s->admission=*config;
    s->admission_stats.enabled=1;
    s->pending_visit=s->running_visit=UINT32_MAX;
    return 0;
}

int leo_scanner_glrt_admission_stats(const leo_scanner_glrt *s,
    leo_scanner_glrt_admission_stats_v1 *out)
{
    if (!s || !out) return -EINVAL;
    *out=s->admission_stats;
    out->pending=out->enabled && s->pending_visit!=UINT32_MAX;
    out->running=out->enabled && !s->failed && s->running_visit!=UINT32_MAX;
    return 0;
}

int leo_scanner_glrt_skip_cause(const leo_scanner_glrt *s, uint64_t visit, uint32_t *out)
{
    if (!s || !out) return -EINVAL;
    if (!s->cooperative_skips) return -ENOTSUP;
    if (visit>=s->known) return -EINVAL;
    if (s->visits[visit].state<DONE) return -EAGAIN;
    *out=s->visits[visit].skip_cause;
    return 0;
}

int leo_scanner_glrt_protection_stats(const leo_scanner_glrt *s,
    leo_scanner_glrt_protection_stats_v1 *out)
{
    if (!s || !out) return -EINVAL;
    *out=s->protection_stats;
    leo_probe_stats pool; leo_probe_pool_stats(s->pool,&pool);
    out->occupied_slots=pool.occupied_slots;
    out->disabled=(uint32_t)s->failed;
    return 0;
}

static void harvest(leo_scanner_glrt *s)
{
    if (!s->failed) {
        for (unsigned j=0;j<LEO_PROBE_RESULTS;++j) {
            leo_probe_result result;
            int ret=leo_probe_read_result(s->pool,&result);
            if (!ret) break;
            if (ret<0 || result.request.sequence>=s->known) { leo_scanner_glrt_fail(s); break; }
            uint32_t index=(uint32_t)result.request.sequence;
            const leo_glrt_classification_v1 *r=&s->visits[index].record;
            const leo_probe_request *q=&result.request;
            if (s->visits[index].state!=WORKING || q->session!=s->config.session ||
                q->generation!=s->config.generation || q->visit!=r->visit ||
                q->valid_start!=r->valid_start || q->valid_end!=r->valid_end ||
                q->rx!=s->config.rx || q->channel!=r->channel || q->edge!=r->edge ||
                q->rate_hz!=s->config.rate_hz ||
                leo_glrt_result_record(&result,s->policy.classification_enabled ? &s->policy : NULL,
                    &s->visits[index].record) ||
                (s->policy.classification_enabled && leo_glrt_result_observation(&result,
                    &s->policy,&s->visits[index].observation))) {
                leo_scanner_glrt_fail(s); break;
            }
            s->visits[index].state=DONE;
            if (s->admission_stats.enabled) {
                if (s->running_visit!=index) { leo_scanner_glrt_fail(s); break; }
                s->running_visit=UINT32_MAX;
            }
        }
        leo_probe_stats stats; leo_probe_pool_stats(s->pool,&stats);
        if (stats.result_dropped) leo_scanner_glrt_fail(s);
    }
    if (s->worker>0) {
        int status;
        pid_t ret=waitpid(s->worker,&status,WNOHANG);
        if (ret==s->worker) {
            s->worker=0;
            if (!s->finished || !WIFEXITED(status) || WEXITSTATUS(status)) leo_scanner_glrt_fail(s);
            /* A normal exit must not strand a submitted request. Its last
             * release-store can precede this waitpid but follow our first poll. */
            if (!s->failed) {
                harvest(s);
                for (uint32_t j=s->sending;j<s->known;++j)
                    if (s->visits[j].state<DONE) { leo_scanner_glrt_fail(s); break; }
            }
        } else if (ret<0 && errno!=EINTR) {
            s->worker=0; leo_scanner_glrt_fail(s);
        }
    }
    /* Accept completed evidence before checking the oldest outstanding job. */
    check_protection(s);
}

int leo_scanner_glrt_capture_pressure(leo_scanner_glrt *s, int pressured)
{
    if (!s || (pressured!=0 && pressured!=1)) return -EINVAL;
    if (!s->protection_stats.enabled) return -ENOTSUP;
    if (s->finished) return -EBUSY;
    harvest(s);
    if (s->failed) return 0;
    if (pressured) {
        if (!s->protection_stats.suspended) ++s->protection_stats.pressure_entries;
        s->protection_stats.suspended=1; s->recovery_count=0;
    } else if (s->protection_stats.suspended &&
        ++s->recovery_count>=s->protection.recovery_blocks) {
        s->protection_stats.suspended=0; s->recovery_count=0;
        ++s->protection_stats.resumptions;
    }
    advance_admission(s);
    return 0;
}

int leo_scanner_glrt_observation(leo_scanner_glrt *s, leo_adaptive_observation_v1 *out)
{
    if (!s || !out) return -EINVAL;
    if (!s->policy.classification_enabled) return -ENOTSUP;
    harvest(s);
    advance_admission(s);
    if (s->observing<s->known && s->visits[s->observing].state>=DONE) {
        *out=s->visits[s->observing++].observation;
        return 1;
    }
    return s->finished && s->observing==s->known ? -ENODATA : 0;
}

/* Do not alter the daemon's process-wide SIGPIPE disposition. A full pipe
 * already contains a wakeup; a dead worker must never terminate acquisition. */
static int wake_worker(leo_scanner_glrt *s)
{
    sigset_t set, previous, pending;
    sigemptyset(&set); sigaddset(&set,SIGPIPE);
    if (pthread_sigmask(SIG_BLOCK,&set,&previous)) return -1;
    int was_pending=sigpending(&pending) || sigismember(&pending,SIGPIPE);
    ssize_t n=write(s->notify,"1",1);
    int error=errno;
    if (n<0 && error==EPIPE && !was_pending) {
        struct timespec zero={0};
        while (sigtimedwait(&set,NULL,&zero)<0 && errno==EINTR) {}
    }
    if (pthread_sigmask(SIG_SETMASK,&previous,NULL)) return -1;
    return n==1 || (n<0 && error==EAGAIN) ? 0 : -1;
}

static unsigned target_for(const leo_scanner_glrt *s, uint32_t index)
{ return s->visits[index].record.channel-1+4*s->visits[index].record.edge; }

static void drop_pending(leo_scanner_glrt *s, enum leo_glrt_reason reason, int intentional)
{
    uint32_t index=s->pending_visit;
    if (index==UINT32_MAX) return;
    leo_probe_request q=request_for(s,index);
    if (leo_probe_release_held(s->pool,s->pending_slot,&q)) { leo_scanner_glrt_fail(s); return; }
    s->pending_visit=UINT32_MAX;
    if (intentional) {
        admission_skip(s,index,reason);
        if (reason==LEO_GLRT_WORKER_BUSY) ++s->protection_stats.backlog_skips;
        else ++s->protection_stats.pressure_skips;
    } else unavailable(s,index,reason);
}

static int pending_expired(const leo_scanner_glrt *s)
{
    uint64_t end=s->visits[s->pending_visit].record.valid_end;
    return s->now_ns-s->pending_ns>(uint64_t)s->admission.maximum_pending_age_ms*1000000 ||
        (s->history_end>end && s->history_end-end>
            (uint64_t)s->config.rate_hz*s->admission.maximum_pending_age_ms/1000);
}

static int freshness_eligible(const leo_scanner_glrt *s, unsigned target)
{
    uint64_t limit=(uint64_t)s->config.rate_hz*s->admission.freshness_trigger_ms/1000;
    if (!s->admission_pressure || s->history_end-s->pressure_source>=limit) return 1;
    uint32_t overdue=0;
    for (unsigned j=0;j<8;++j) {
        if (!(s->seen_targets&(1u<<j))) continue;
        if (!(s->dispatched_targets&(1u<<j)) ||
            s->history_end-s->last_dispatch_source[j]>=limit) overdue|=1u<<j;
    }
    return !overdue || (overdue&(1u<<target));
}

static void advance_admission(leo_scanner_glrt *s)
{
    if (!s->admission_stats.enabled || s->failed) return;
    if (s->pending_visit!=UINT32_MAX) {
        if (s->protection_stats.suspended) {
            ++s->admission_stats.pressure_drops;
            drop_pending(s,LEO_GLRT_INCOMPLETE_SEARCH,1);
        } else if (pending_expired(s)) {
            ++s->admission_stats.expired;
            drop_pending(s,LEO_GLRT_WORKER_BUSY,1);
        } else if (s->running_visit==UINT32_MAX) {
            uint32_t index=s->pending_visit;
            unsigned target=target_for(s,index);
            if (!freshness_eligible(s,target)) {
                ++s->admission_stats.freshness_skips;
                drop_pending(s,LEO_GLRT_WORKER_BUSY,1);
            } else {
                leo_probe_request q=request_for(s,index);
                if (leo_probe_publish_held(s->pool,s->pending_slot,&q)) {
                    leo_scanner_glrt_fail(s); return;
                }
                s->pending_visit=UINT32_MAX; s->running_visit=index;
                s->visits[index].state=WORKING; s->visits[index].submitted_ns=s->now_ns;
                s->last_dispatch_ns[target]=s->now_ns;
                s->last_dispatch_source[target]=s->visits[index].record.valid_end;
                s->dispatched_targets|=1u<<target;
                ++s->admission_stats.dispatched;
                if (wake_worker(s)) { leo_scanner_glrt_fail(s); return; }
            }
        }
    }
    /* Keep the worker's notification pipe open while terminal pending work can
     * still be admitted. Closing early would expose HELD storage at EOF. */
    if (s->finished && s->pending_visit==UINT32_MAX && s->notify>=0) {
        close(s->notify); s->notify=-1;
    }
}

static void accept_held(leo_scanner_glrt *s, uint32_t index)
{
    unsigned target=target_for(s,index);
    s->visits[index].state=HELD;
    s->seen_targets|=1u<<target;
    if (s->running_visit!=UINT32_MAX) {
        s->admission_pressure=1; s->pressure_source=s->history_end;
    }
    advance_admission(s);
    if (s->failed) return;
    if (s->pending_visit!=UINT32_MAX) {
        unsigned previous=target_for(s,s->pending_visit);
        int replace=!(s->dispatched_targets&(1u<<target)) ?
            !!(s->dispatched_targets&(1u<<previous)) :
            ((s->dispatched_targets&(1u<<previous)) &&
             s->last_dispatch_ns[target]<s->last_dispatch_ns[previous]);
        if (!replace) {
            leo_probe_request q=request_for(s,index);
            if (leo_probe_release_held(s->pool,s->collector.slot,&q)) {
                leo_scanner_glrt_fail(s); return;
            }
            admission_skip(s,index,LEO_GLRT_WORKER_BUSY);
            ++s->protection_stats.backlog_skips;
            return;
        }
        ++s->admission_stats.replacements;
        drop_pending(s,LEO_GLRT_WORKER_BUSY,1);
        if (s->failed) return;
    }
    s->pending_visit=index; s->pending_slot=s->collector.slot; s->pending_ns=s->now_ns;
    advance_admission(s);
}

static void collect_available(leo_scanner_glrt *s)
{
    while (!s->failed && s->collecting<s->known && s->have_history) {
        uint32_t index=s->collecting;
        struct visit_record *v=&s->visits[index];
        uint64_t expected=v->record.valid_start+s->collector.copied;
        if (v->state==PLANNED) expected=v->record.valid_start;
        if (expected>=s->history_end) break;
        if (s->protection_stats.suspended) {
            leo_probe_abort(&s->collector);
            admission_skip(s,index,LEO_GLRT_INCOMPLETE_SEARCH);
            ++s->protection_stats.pressure_skips; ++s->collecting; continue;
        }
        if (expected<s->history_start) {
            leo_probe_abort(&s->collector);
            unavailable(s,index,LEO_GLRT_INVALID_INPUT); ++s->collecting; continue;
        }
        if (v->state==PLANNED) {
            if (s->protection_stats.enabled) {
                leo_probe_stats pool; leo_probe_pool_stats(s->pool,&pool);
                if (pool.occupied_slots>=s->protection.max_occupied_slots ||
                    (s->oldest_pending<s->collecting &&
                     s->visits[s->oldest_pending].state==WORKING &&
                     s->now_ns-s->visits[s->oldest_pending].submitted_ns>=
                         (uint64_t)s->protection.admission_age_ms*1000000)) {
                    admission_skip(s,index,LEO_GLRT_WORKER_BUSY);
                    ++s->protection_stats.backlog_skips; ++s->collecting; continue;
                }
            }
            leo_probe_request q=request_for(s,index);
            int ret=leo_probe_begin(&s->collector,s->pool,&q);
            if (ret!=1) {
                unavailable(s,index,ret ? LEO_GLRT_INVALID_INPUT : LEO_GLRT_WORKER_BUSY);
                ++s->collecting; continue;
            }
            v->state=COLLECTING;
            if (s->protection_stats.enabled) {
                leo_probe_stats pool; leo_probe_pool_stats(s->pool,&pool);
                if (pool.occupied_slots>s->protection_stats.peak_occupied_slots)
                    s->protection_stats.peak_occupied_slots=pool.occupied_slots;
            }
        }
        size_t offset=(size_t)(expected%s->history_capacity);
        size_t count=(size_t)(s->history_end-expected);
        if (count>s->history_capacity-offset) count=s->history_capacity-offset;
        int ret=s->admission_stats.enabled ?
            leo_probe_feed_held(&s->collector,expected,s->history+2*offset,count,2,0) :
            leo_probe_feed(&s->collector,expected,s->history+2*offset,count,2,0);
        if (ret<0) { unavailable(s,index,LEO_GLRT_INVALID_INPUT); ++s->collecting; }
        else if (ret==1) {
            if (s->admission_stats.enabled) {
                ++s->collecting;
                accept_held(s,index);
                continue;
            }
            v->submitted_ns=s->now_ns;
            v->state=WORKING; ++s->collecting;
            if (wake_worker(s)) leo_scanner_glrt_fail(s);
        }
    }
}

int leo_scanner_glrt_visit(leo_scanner_glrt *s, uint64_t visit,
    uint64_t start, uint64_t end, uint32_t channel, uint32_t edge)
{
    if (!s || s->finished || visit!=s->known || s->known>=s->config.maximum_visits ||
        end<=start || end-start!=s->config.rate_hz/50*6 || channel<1 || channel>4 || edge>1 ||
        (s->known && start<s->visits[s->known-1].record.valid_end)) return -EINVAL;
    uint32_t index=s->known++;
    s->visits[index].record=(leo_glrt_classification_v1){.visit=visit,.valid_start=start,
        .valid_end=end,.channel=(uint8_t)channel,.edge=(uint8_t)edge};
    unavailable(s,index,s->failed ? LEO_GLRT_WORKER_FAILED : LEO_GLRT_INCOMPLETE_SEARCH);
    if (!s->failed) s->visits[index].state=PLANNED;
    else s->collecting=s->known;
    harvest(s);
    advance_admission(s);
    collect_available(s);
    return 0;
}

int leo_scanner_glrt_block(leo_scanner_glrt *s, uint64_t first,
    const int16_t *iq, size_t count, size_t stride, size_t rx_offset)
{
    if (!s || s->finished || !iq || !count || count>s->config.maximum_block_samples ||
        count>UINT64_MAX-first || stride!=4 || rx_offset!=2*s->config.rx) return -EINVAL;
    harvest(s);
    if (s->failed) return 0;
    if (s->have_history && first<s->history_end) return -EINVAL;
    if (!s->have_history || first!=s->history_end) s->history_start=first;
    s->have_history=1;
    uint64_t end=first+count;
    if (s->protection_stats.suspended) {
        /* The caller retains/forwards its original dual-RX IQ. Only this
         * advisory copy is omitted; invalidate history rather than reuse it. */
        s->history_start=s->history_end=end;
        ++s->protection_stats.history_blocks_skipped;
        advance_admission(s);
        collect_available(s);
        return 0;
    }
    size_t offset=(size_t)(first%s->history_capacity), copied=0;
    while (copied<count) {
        size_t n=count-copied;
        if (n>s->history_capacity-offset) n=s->history_capacity-offset;
        for (size_t j=0;j<n;++j) {
            s->history[2*(offset+j)]=iq[(copied+j)*stride+rx_offset];
            s->history[2*(offset+j)+1]=iq[(copied+j)*stride+rx_offset+1];
        }
        copied+=n; offset=0;
    }
    s->history_end=end;
    if (end-s->history_start>s->history_capacity) s->history_start=end-s->history_capacity;
    advance_admission(s);
    collect_available(s);
    return 0;
}

int leo_scanner_glrt_finish(leo_scanner_glrt *s, int cancelled)
{
    if (!s || (cancelled!=0 && cancelled!=1)) return -EINVAL;
    if (s->finished) return 0;
    harvest(s); collect_available(s);
    leo_probe_abort(&s->collector);
    for (uint32_t j=s->collecting;j<s->known;++j)
        if (s->visits[j].state<WORKING)
            unavailable(s,j,cancelled ? LEO_GLRT_CANCELLED : LEO_GLRT_INCOMPLETE_SEARCH);
    s->collecting=s->known;
    s->finished=1;
    if (s->admission_stats.enabled) {
        if (cancelled) drop_pending(s,LEO_GLRT_CANCELLED,0);
        advance_admission(s);
    } else if (s->notify>=0) { close(s->notify); s->notify=-1; }
    return 0;
}

static ssize_t emit(leo_scanner_glrt *s, const void *legacy, size_t legacy_bytes,
    void *output, size_t capacity, int draining)
{
    if (!s || !output || legacy_bytes>LEO_GLRT_FRAME_MAX_BYTES-LEO_GLRT_FRAME_HEADER_BYTES ||
        (!draining && (!legacy || !legacy_bytes)) || s->final) return -EINVAL;
    harvest(s);
    advance_admission(s);
    leo_glrt_frame_v1 f={.session=s->config.session,.generation=s->config.generation,
        .frame_sequence=s->frame_sequence,.result_sequence_limit=s->known,
        .legacy_metadata=legacy,.legacy_bytes=(uint32_t)legacy_bytes};
    memcpy(f.algorithm_sha256,s->config.algorithm_sha256,32);
    memcpy(f.configuration_sha256,s->config.configuration_sha256,32);
    if (draining) f.flags|=LEO_GLRT_FRAME_DRAIN;
    if (s->failed) f.flags|=LEO_GLRT_FRAME_DETECTOR_FAILED;
    while (f.result_count<LEO_GLRT_FRAME_MAX_RECORDS && s->sending+f.result_count<s->known &&
        s->visits[s->sending+f.result_count].state==DONE) {
        f.results[f.result_count]=s->visits[s->sending+f.result_count].record;
        ++f.result_count;
    }
    if (draining && s->sending+f.result_count==s->known && (!s->worker || s->failed))
        f.flags|=LEO_GLRT_FRAME_FINAL;
    if (draining && !f.result_count && !(f.flags&LEO_GLRT_FRAME_FINAL)) return -EAGAIN;
    size_t bytes=LEO_GLRT_FRAME_HEADER_BYTES+legacy_bytes+f.result_count*LEO_GLRT_RECORD_BYTES;
    if (bytes>capacity) return -ENOSPC;
    if (leo_glrt_frame_encode(&f,output,capacity,&bytes)) return -EINVAL;
    for (unsigned j=0;j<f.result_count;++j) s->visits[s->sending++].state=SENT;
    ++s->frame_sequence;
    s->final=!!(f.flags&LEO_GLRT_FRAME_FINAL);
    return (ssize_t)bytes;
}

ssize_t leo_scanner_glrt_frame(leo_scanner_glrt *s, const void *legacy,
    size_t legacy_bytes, void *output, size_t capacity)
{ return emit(s,legacy,legacy_bytes,output,capacity,0); }

ssize_t leo_scanner_glrt_drain(leo_scanner_glrt *s, void *output, size_t capacity)
{
    if (!s || !output) return -EINVAL;
    if (!s->finished) return -EBUSY;
    if (s->final) return -ENODATA;
    return emit(s,NULL,0,output,capacity,1);
}

static int trusted_file(const char *path, int executable)
{
    if (!path || path[0]!='/') return -EINVAL;
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return -errno;
    struct stat st;
    if (fd<3 || fstat(fd,&st) || !S_ISREG(st.st_mode) ||
        (st.st_uid!=0 && st.st_uid!=geteuid()) || (st.st_mode&0022) ||
        (executable && !(st.st_mode&0111))) { close(fd); return -EPERM; }
    return fd;
}

void leo_scanner_glrt_close(leo_scanner_glrt *s)
{
    if (!s) return;
    if (s->notify>=0) close(s->notify);
    if (s->worker>0) {
        /* Only our unreaped child can still own this PID. No process search
         * or unrelated daemon is ever signalled. Close is outside capture. */
        (void)kill(s->worker,SIGKILL);
        while (waitpid(s->worker,NULL,0)<0 && errno==EINTR) {}
    }
    if (s->pool && s->pool!=MAP_FAILED) munmap(s->pool,leo_dwell_pool_bytes());
    free(s->history); free(s->visits); free(s);
}

/* After fork in a multithreaded daemon, use only async-signal-safe operations.
 * Close unrelated descriptors BEFORE exec, not merely inside worker main.
 * close_range is optional; the existing older radio kernel uses the bounded
 * descriptor-limit fallback. The parent's startup deadline covers both. */
static void child_close_descriptors(const int keep[4], int limit)
{
    unsigned int first=3;
    for (unsigned j=0;j<=4;++j) {
        unsigned int last=j<4 ? (unsigned int)keep[j]-1 : UINT_MAX;
        if (first<=last) {
#ifdef SYS_close_range
            if (syscall(SYS_close_range,first,last,0))
#endif
                for (unsigned int fd=first;fd<=last && fd<(unsigned int)limit;++fd)
                    close((int)fd);
        }
        if (j<4) first=(unsigned int)keep[j]+1;
    }
    close(STDIN_FILENO);
}

static int open_session(leo_scanner_glrt **output,
    const leo_scanner_glrt_config_v1 *config, const char *worker_path, const char *template_path,
    const leo_scanner_glrt_positive_policy_v1 *policy)
{
    if (!output || !config || !config->session || !config->generation || config->rx!=1 ||
        (config->rate_hz!=2500000 && config->rate_hz!=5000000) || !config->maximum_visits ||
        config->maximum_visits>LEO_SCANNER_GLRT_MAX_VISITS || !config->maximum_block_samples ||
        config->maximum_block_samples>LEO_SCANNER_GLRT_MAX_BLOCK_SAMPLES) return -EINVAL;
    uint8_t algorithm=0,configuration=0;
    for (unsigned j=0;j<32;++j) { algorithm|=config->algorithm_sha256[j]; configuration|=config->configuration_sha256[j]; }
    if (!algorithm || !configuration) return -EINVAL;
    int binary=trusted_file(worker_path,1);
    if (binary<0) return binary;
    int templates=trusted_file(template_path,0);
    if (templates<0) { close(binary); return templates; }
    int shared=-1, notify[2]={-1,-1}, ready[2]={-1,-1}, error=-ENOMEM;
    leo_scanner_glrt *s=calloc(1,sizeof(*s));
    if (!s) goto done;
    s->notify=-1; s->config=*config;
    if (policy) s->policy=(leo_glrt_decision_policy){.minimum_exact_score=policy->minimum_exact_score,
        .minimum_margin=policy->minimum_margin,.classification_enabled=1,.absence_enabled=0};
    s->history_capacity=2*(size_t)config->maximum_block_samples+config->rate_hz/50*6;
    if (posix_memalign((void **)&s->history,64,s->history_capacity*2*sizeof(int16_t))) goto done;
    memset(s->history,0,s->history_capacity*2*sizeof(int16_t));
    s->visits=calloc(config->maximum_visits,sizeof(*s->visits));
    if (!s->visits) goto done;
    char path[]="/tmp/leo-glrt-pool-XXXXXX";
    shared=mkostemp(path,O_CLOEXEC);
    if (shared<0) { error=-errno; goto done; }
    if (unlink(path) || ftruncate(shared,(off_t)leo_dwell_pool_bytes())) { error=-errno; goto done; }
    s->pool=mmap(NULL,leo_dwell_pool_bytes(),PROT_READ|PROT_WRITE,MAP_SHARED,shared,0);
    if (s->pool==MAP_FAILED) { error=-errno; goto done; }
    if (leo_dwell_pool_init(s->pool,config->session,config->generation,config->rate_hz,config->rx)) goto done;
    if (pipe2(notify,O_CLOEXEC|O_NONBLOCK) || pipe2(ready,O_CLOEXEC|O_NONBLOCK)) { error=-errno; goto done; }
    if (shared<3 || notify[0]<3 || notify[1]<3 || ready[0]<3 || ready[1]<3) { error=-EINVAL; goto done; }
    char mapping_arg[24], notify_arg[24], template_arg[24], parent_arg[24];
    snprintf(mapping_arg,sizeof(mapping_arg),"%d",shared);
    snprintf(notify_arg,sizeof(notify_arg),"%d",notify[0]);
    snprintf(template_arg,sizeof(template_arg),"%d",templates);
    snprintf(parent_arg,sizeof(parent_arg),"%ld",(long)getpid());
    char *arguments[]={(char *)worker_path,mapping_arg,notify_arg,template_arg,parent_arg,NULL};
    struct rlimit descriptors;
    if (getrlimit(RLIMIT_NOFILE,&descriptors) || descriptors.rlim_max>INT_MAX) {
        error=-EOVERFLOW; goto done;
    }
    int keep[4]={binary,shared,notify[0],templates};
    for (unsigned j=0;j<4;++j) for (unsigned k=j+1;k<4;++k)
        if (keep[k]<keep[j]) { int swap=keep[j]; keep[j]=keep[k]; keep[k]=swap; }
    s->worker=fork();
    if (s->worker<0) { error=-errno; s->worker=0; goto done; }
    if (!s->worker) {
        if (fcntl(shared,F_SETFD,0) || fcntl(notify[0],F_SETFD,0) ||
            fcntl(templates,F_SETFD,0) || dup2(ready[1],STDOUT_FILENO)<0) _exit(2);
        child_close_descriptors(keep,(int)descriptors.rlim_max);
        fexecve(binary,arguments,environ);
        _exit(2);
    }
    close(notify[0]); notify[0]=-1;
    close(ready[1]); ready[1]=-1;
    struct timespec began,now;
    if (clock_gettime(CLOCK_MONOTONIC,&began)) { error=-errno; goto done; }
    char handshake[6]; size_t received=0;
    while (received<sizeof(handshake)) {
        if (clock_gettime(CLOCK_MONOTONIC,&now)) { error=-errno; goto done; }
        long elapsed=(now.tv_sec-began.tv_sec)*1000+(now.tv_nsec-began.tv_nsec)/1000000;
        if (elapsed>=5000) { error=-ETIMEDOUT; goto done; }
        struct pollfd event={.fd=ready[0],.events=POLLIN};
        int ret=poll(&event,1,(int)(5000-elapsed));
        if (ret<0 && errno==EINTR) continue;
        if (ret<=0) { error=ret ? -errno : -ETIMEDOUT; goto done; }
        ssize_t n=read(ready[0],handshake+received,sizeof(handshake)-received);
        if (n<0 && (errno==EAGAIN || errno==EINTR)) continue;
        if (n<=0) { error=-EIO; goto done; }
        received+=(size_t)n;
    }
    if (memcmp(handshake,"ready\n",6)) { error=-EPROTO; goto done; }
    s->notify=notify[1]; notify[1]=-1;
    *output=s; s=NULL; error=0;
done:
    close(binary); close(templates);
    if (shared>=0) close(shared);
    for (unsigned j=0;j<2;++j) { if (notify[j]>=0) close(notify[j]); if (ready[j]>=0) close(ready[j]); }
    leo_scanner_glrt_close(s);
    return error;
}

int leo_scanner_glrt_open(leo_scanner_glrt **output,
    const leo_scanner_glrt_config_v1 *config, const char *worker_path, const char *template_path)
{ return open_session(output,config,worker_path,template_path,NULL); }

int leo_scanner_glrt_open_positive(leo_scanner_glrt **output,
    const leo_scanner_glrt_config_v1 *config, const char *worker_path, const char *template_path,
    const leo_scanner_glrt_positive_policy_v1 *policy)
{
    if (!policy || !isfinite(policy->minimum_exact_score) || policy->minimum_exact_score<0 ||
        !isfinite(policy->minimum_margin) || policy->minimum_margin<=0) return -EINVAL;
    return open_session(output,config,worker_path,template_path,policy);
}
