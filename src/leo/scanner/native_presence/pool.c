#include "pool.h"
#include <stdatomic.h>
#include <string.h>

#if ATOMIC_INT_LOCK_FREE != 2
#error "Presence handoff requires lock-free 32-bit atomic integers"
#endif

/* Private same-build ABI: older workers must reject HELD-capable mappings
 * during startup, not silently apply FIFO semantics to managed admission. */
#define LEO_POOL_MAGIC UINT32_C(0x4c505033)

enum { FREE, FILLING, READY, WORKING, HELD };
typedef struct {
    _Alignas(64) _Atomic uint32_t state;
    leo_probe_request request;
} probe_slot;

struct leo_probe_pool {
    uint32_t magic, abi_size;
    uint64_t session, generation;
    uint32_t rate, dwell, rx;
    _Atomic uint32_t held_mode;
    _Alignas(64) uint32_t producer_head;
    _Atomic uint32_t submitted, busy, invalid, aborted;
    _Alignas(64) uint32_t worker_tail;
    _Atomic uint32_t completed, result_dropped, result_head;
    _Alignas(64) _Atomic uint32_t result_tail;
    probe_slot slots[LEO_PROBE_SLOTS];
    leo_probe_result results[LEO_PROBE_RESULTS];
    /* Both capacities are multiples of a cache line, so all three CI16
     * regions remain aligned. Legacy mode need not allocate full dwells. */
    _Alignas(64) int16_t iq[];
};

size_t leo_probe_pool_bytes(void)
{ return sizeof(leo_probe_pool)+LEO_PROBE_SLOTS*LEO_PROBE_MAX_SAMPLES*2*sizeof(int16_t); }
size_t leo_dwell_pool_bytes(void)
{ return sizeof(leo_probe_pool)+LEO_PROBE_SLOTS*LEO_DWELL_MAX_SAMPLES*2*sizeof(int16_t); }

static int initialize(leo_probe_pool *p, uint64_t session, uint64_t generation,
    uint32_t rate, uint32_t dwell, uint32_t rx)
{
    if (!p || (uintptr_t)p%64 || !session || !generation || rx>1 ||
        (rate!=2500000 && rate!=5000000)) return -1;
    size_t bytes=dwell ? leo_dwell_pool_bytes() : leo_probe_pool_bytes();
    memset(p,0,bytes);
    p->magic=LEO_POOL_MAGIC; p->abi_size=(uint32_t)bytes;
    p->session=session; p->generation=generation; p->rate=rate;
    p->dwell=dwell; p->rx=rx;
    atomic_init(&p->held_mode,0);
    atomic_init(&p->submitted,0); atomic_init(&p->busy,0); atomic_init(&p->invalid,0);
    atomic_init(&p->aborted,0); atomic_init(&p->completed,0); atomic_init(&p->result_dropped,0);
    atomic_init(&p->result_head,0); atomic_init(&p->result_tail,0);
    for (unsigned j=0; j<LEO_PROBE_SLOTS; ++j) atomic_init(&p->slots[j].state,FREE);
    return 0;
}

int leo_probe_pool_init(leo_probe_pool *p, uint64_t session, uint64_t generation, uint32_t rate)
{ return initialize(p,session,generation,rate,0,1); }

int leo_dwell_pool_init(leo_probe_pool *p, uint64_t session, uint64_t generation, uint32_t rate, uint32_t rx)
{ return initialize(p,session,generation,rate,1,rx); }

static int configured(const leo_probe_pool *p)
{
    return p && p->magic==LEO_POOL_MAGIC && p->dwell<=1 && p->rx<=1 &&
        atomic_load_explicit(&p->held_mode,memory_order_acquire)<=1 &&
        p->abi_size==(p->dwell ? leo_dwell_pool_bytes() : leo_probe_pool_bytes()) &&
        p->session && p->generation && (p->rate==2500000 || p->rate==5000000);
}

int leo_probe_pool_configuration(const leo_probe_pool *p, uint64_t *session, uint64_t *generation, uint32_t *rate)
{
    if (!session || !generation || !rate || !configured(p)) return -1;
    *session=p->session; *generation=p->generation; *rate=p->rate;
    return 0;
}

int leo_probe_pool_geometry(const leo_probe_pool *p, uint32_t *dwell, uint32_t *rx)
{
    if (!dwell || !rx || !configured(p)) return -1;
    *dwell=p->dwell; *rx=p->rx;
    return 0;
}

int leo_dwell_pool_enable_held(leo_probe_pool *p)
{
    if (!configured(p) || !p->dwell || atomic_load(&p->held_mode) ||
        atomic_load(&p->submitted) || p->producer_head) return -1;
    for (unsigned j=0;j<LEO_PROBE_SLOTS;++j)
        if (atomic_load(&p->slots[j].state)!=FREE) return -1;
    atomic_store_explicit(&p->held_mode,1,memory_order_release);
    return 0;
}

static int16_t *slot_iq(leo_probe_pool *p, uint32_t index)
{
    return p->iq+index*2*(p->dwell ? LEO_DWELL_MAX_SAMPLES : LEO_PROBE_MAX_SAMPLES);
}

void leo_probe_pool_stats(const leo_probe_pool *p, leo_probe_stats *out)
{
    if (!p || !out) return;
    uint32_t tail=atomic_load(&p->result_tail), head=atomic_load(&p->result_head);
    uint32_t pending=head-tail;
    *out=(leo_probe_stats){
        .submitted=atomic_load(&p->submitted), .busy=atomic_load(&p->busy),
        .invalid=atomic_load(&p->invalid), .aborted=atomic_load(&p->aborted),
        .completed=atomic_load(&p->completed), .result_dropped=atomic_load(&p->result_dropped),
        .pending_results=pending>LEO_PROBE_RESULTS ? LEO_PROBE_RESULTS : pending,
    };
    for (unsigned j=0; j<LEO_PROBE_SLOTS; ++j)
        out->occupied_slots+=atomic_load(&p->slots[j].state)!=FREE;
}

static int same_request(const leo_probe_request *a, const leo_probe_request *b)
{
    /* Padding bytes are not part of identity, even within a same-build ABI. */
    return a->session==b->session && a->generation==b->generation && a->sequence==b->sequence &&
        a->visit==b->visit && a->valid_start==b->valid_start && a->valid_end==b->valid_end &&
        a->probe_start==b->probe_start && a->rate_hz==b->rate_hz && a->sample_count==b->sample_count &&
        a->rx==b->rx && a->channel==b->channel && a->edge==b->edge;
}

static int valid_request(const leo_probe_pool *p, const leo_probe_request *r)
{
    return r && r->session==p->session && r->generation==p->generation && r->rate_hz==p->rate &&
        r->rx<=1 && (!p->dwell || r->rx==p->rx) &&
        r->channel>=1 && r->channel<=4 && r->edge<=1 &&
        r->sample_count==p->rate/50*(p->dwell ? 6u : 1u) &&
        r->valid_end>=r->valid_start && r->valid_end-r->valid_start==p->rate*120/1000 &&
        r->probe_start>=r->valid_start && r->probe_start<=r->valid_end &&
        r->sample_count<=r->valid_end-r->probe_start;
}

int leo_probe_begin(leo_probe_collector *c, leo_probe_pool *p, const leo_probe_request *request)
{
    if (!c || !p) return -1;
    if (c->active || !valid_request(p,request)) { atomic_fetch_add(&p->invalid,1); return -1; }
    uint32_t index=p->producer_head%LEO_PROBE_SLOTS;
    if (atomic_load_explicit(&p->held_mode,memory_order_acquire)) {
        for (unsigned j=0;j<LEO_PROBE_SLOTS;++j) {
            uint32_t candidate=(index+j)%LEO_PROBE_SLOTS;
            if (atomic_load_explicit(&p->slots[candidate].state,memory_order_acquire)==FREE) {
                index=candidate; break;
            }
        }
    }
    probe_slot *slot=&p->slots[index];
    if (atomic_load_explicit(&slot->state,memory_order_acquire)!=FREE) {
        atomic_fetch_add(&p->busy,1); return 0;
    }
    slot->request=*request;
    atomic_store_explicit(&slot->state,FILLING,memory_order_relaxed);
    *c=(leo_probe_collector){.pool=p,.slot=index,.active=1};
    if (atomic_load(&p->held_mode)) ++p->producer_head;
    return 1;
}

void leo_probe_abort(leo_probe_collector *c)
{
    if (!c || !c->active) return;
    atomic_fetch_add(&c->pool->aborted,1);
    atomic_store_explicit(&c->pool->slots[c->slot].state,FREE,memory_order_release);
    c->active=0;
}

static int feed(leo_probe_collector *c, uint64_t block, const int16_t *samples,
    size_t count, size_t stride, size_t rx_offset, int held)
{
    if (!c || !c->active) return -1;
    leo_probe_pool *p=c->pool;
    if ((int)atomic_load_explicit(&p->held_mode,memory_order_acquire)!=held) return -1;
    if (!samples || !count || stride<2 || stride>16 || rx_offset>stride-2 ||
        count>SIZE_MAX/stride/sizeof(int16_t) || count>UINT64_MAX-block) {
        atomic_fetch_add(&p->invalid,1); leo_probe_abort(c); return -1;
    }
    probe_slot *slot=&p->slots[c->slot];
    uint64_t expected=slot->request.probe_start+c->copied, end=block+count;
    if (end<=expected) return 0;
    if (block>expected) { leo_probe_abort(c); return -1; }
    size_t offset=(size_t)(expected-block), remaining=slot->request.sample_count-c->copied;
    size_t available=count-offset, copied=available<remaining ? available : remaining;
    const int16_t *input=samples+offset*stride+rx_offset;
    int16_t *output=slot_iq(p,c->slot)+2*c->copied;
    if (stride==2) memcpy(output,input,copied*2*sizeof(int16_t));
    else for (size_t k=0; k<copied; ++k) {
        output[2*k]=input[k*stride]; output[2*k+1]=input[k*stride+1];
    }
    c->copied+=(uint32_t)copied;
    if (c->copied<slot->request.sample_count) return 0;
    atomic_store_explicit(&slot->state,held ? HELD : READY,memory_order_release);
    if (!held) { ++p->producer_head; atomic_fetch_add(&p->submitted,1); }
    c->active=0;
    return 1;
}

int leo_probe_feed(leo_probe_collector *c, uint64_t block, const int16_t *samples,
    size_t count, size_t stride, size_t rx_offset)
{ return feed(c,block,samples,count,stride,rx_offset,0); }

int leo_probe_feed_held(leo_probe_collector *c, uint64_t block, const int16_t *samples,
    size_t count, size_t stride, size_t rx_offset)
{ return feed(c,block,samples,count,stride,rx_offset,1); }

static int held_change(leo_probe_pool *p, uint32_t index, const leo_probe_request *request, int publish)
{
    if (!configured(p) || !atomic_load(&p->held_mode) || index>=LEO_PROBE_SLOTS || !request ||
        atomic_load_explicit(&p->slots[index].state,memory_order_acquire)!=HELD ||
        !same_request(&p->slots[index].request,request)) return -1;
    if (publish) atomic_fetch_add(&p->submitted,1);
    else atomic_fetch_add(&p->aborted,1);
    atomic_store_explicit(&p->slots[index].state,publish ? READY : FREE,memory_order_release);
    return 0;
}

int leo_probe_publish_held(leo_probe_pool *p, uint32_t index, const leo_probe_request *request)
{ return held_change(p,index,request,1); }

int leo_probe_release_held(leo_probe_pool *p, uint32_t index, const leo_probe_request *request)
{ return held_change(p,index,request,0); }

int leo_probe_take(leo_probe_pool *p, uint32_t *index, leo_probe_request *request, const int16_t **iq)
{
    if (!p || !index || !request || !iq) return -1;
    uint32_t selected=p->worker_tail%LEO_PROBE_SLOTS;
    if (atomic_load_explicit(&p->held_mode,memory_order_acquire)) {
        selected=LEO_PROBE_SLOTS;
        for (unsigned j=0;j<LEO_PROBE_SLOTS;++j) {
            if (atomic_load_explicit(&p->slots[j].state,memory_order_acquire)==READY &&
                (selected==LEO_PROBE_SLOTS || p->slots[j].request.sequence<p->slots[selected].request.sequence))
                selected=j;
        }
        if (selected==LEO_PROBE_SLOTS) return 0;
    }
    probe_slot *slot=&p->slots[selected];
    if (atomic_load_explicit(&slot->state,memory_order_acquire)!=READY) return 0;
    atomic_store_explicit(&slot->state,WORKING,memory_order_relaxed);
    *index=selected; *request=slot->request; *iq=slot_iq(p,selected);
    ++p->worker_tail;
    return 1;
}

int leo_probe_complete(leo_probe_pool *p, uint32_t index, const leo_probe_result *result)
{
    if (!p || !result || index>=LEO_PROBE_SLOTS ||
        atomic_load(&p->slots[index].state)!=WORKING ||
        !same_request(&p->slots[index].request,&result->request) ||
        (result->status!=0 && result->status!=-1)) return -1;
    uint32_t head=atomic_load_explicit(&p->result_head,memory_order_relaxed);
    uint32_t tail=atomic_load_explicit(&p->result_tail,memory_order_acquire);
    if (head-tail>=LEO_PROBE_RESULTS) atomic_fetch_add(&p->result_dropped,1);
    else {
        p->results[head%LEO_PROBE_RESULTS]=*result;
        atomic_store_explicit(&p->result_head,head+1,memory_order_release);
    }
    atomic_fetch_add(&p->completed,1);
    atomic_store_explicit(&p->slots[index].state,FREE,memory_order_release);
    return 0;
}

int leo_probe_read_result(leo_probe_pool *p, leo_probe_result *result)
{
    if (!p || !result) return -1;
    uint32_t tail=atomic_load_explicit(&p->result_tail,memory_order_relaxed);
    if (tail==atomic_load_explicit(&p->result_head,memory_order_acquire)) return 0;
    *result=p->results[tail%LEO_PROBE_RESULTS];
    atomic_store_explicit(&p->result_tail,tail+1,memory_order_release);
    return 1;
}
