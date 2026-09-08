/* Private, same-build shared-memory handoff. Not a persisted/wire contract.
 * One capture producer, one detector consumer, one result reader. No function
 * allocates, waits, controls hardware, or retains the caller's sample buffer. */
#ifndef LEO_SCANNER_PRESENCE_POOL_H
#define LEO_SCANNER_PRESENCE_POOL_H
#include <stddef.h>
#include <stdint.h>
#include "../../analysis/native_presence/presence.h"

#define LEO_PROBE_SLOTS 3
#define LEO_PROBE_RESULTS 64
#define LEO_PROBE_MAX_SAMPLES 100000

typedef struct {
    uint64_t session, generation, sequence, visit;
    uint64_t valid_start, valid_end, probe_start;
    uint32_t rate_hz, sample_count, rx, channel, edge;
} leo_probe_request;

typedef struct {
    leo_probe_request request;
    int32_t status; /* 0: computed candidate evidence; -1: detector failure. */
    leo_presence_result evidence;
    leo_presence_nuisance nuisance;
} leo_probe_result;

typedef struct {
    uint32_t submitted, busy, invalid, aborted, completed, result_dropped;
    uint32_t pending_results, occupied_slots;
} leo_probe_stats;

typedef struct leo_probe_pool leo_probe_pool;
typedef struct {
    leo_probe_pool *pool;
    uint32_t slot, copied, active;
} leo_probe_collector;

/* Mapping must be page-aligned, shared, and at least pool_bytes() bytes long.
 * Initialize only before exposing it to any producer/consumer. */
size_t leo_probe_pool_bytes(void);
int leo_probe_pool_init(leo_probe_pool *, uint64_t session, uint64_t generation, uint32_t rate);
int leo_probe_pool_configuration(const leo_probe_pool *, uint64_t *session, uint64_t *generation, uint32_t *rate);
void leo_probe_pool_stats(const leo_probe_pool *, leo_probe_stats *);

/* Zero-initialize the collector before its first begin call.
 * begin: 1 accepted, 0 pool full (unknown check), -1 invalid/active collector.
 * feed: 1 probe completed, 0 pending/no overlap, -1 invalid or counter gap.
 * feed accepts a selected CI16 pair inside a strided interleaved block; prefix
 * samples before the probe and duplicated prefixes are never copied twice. */
int leo_probe_begin(leo_probe_collector *, leo_probe_pool *, const leo_probe_request *);
int leo_probe_feed(leo_probe_collector *, uint64_t block_counter,
    const int16_t *samples, size_t frame_count, size_t stride_shorts, size_t rx_offset_shorts);
void leo_probe_abort(leo_probe_collector *);

/* take returns 1 and a pool-owned immutable probe until complete(), 0 if none.
 * Only the detector consumer calls take/complete. The result reader receives a
 * copy. Full result retention drops new evidence with an observable counter,
 * freeing the probe slot immediately; it never blocks capture or the worker. */
int leo_probe_take(leo_probe_pool *, uint32_t *slot, leo_probe_request *, const int16_t **samples);
int leo_probe_complete(leo_probe_pool *, uint32_t slot, const leo_probe_result *);
int leo_probe_read_result(leo_probe_pool *, leo_probe_result *);
#endif
