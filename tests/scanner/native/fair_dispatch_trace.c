/* Test-only owner publication trace. The real pool and request stay intact. */
#define _POSIX_C_SOURCE 200809L
#include "pool.h"
#include <stdint.h>
#include <time.h>

typedef struct {
    uint64_t visit, valid_end, published_ns;
    uint32_t target, unused;
} test_dispatch;
static test_dispatch records[2500];
static uint32_t count;

int __real_leo_probe_publish_held(leo_probe_pool *, uint32_t, const leo_probe_request *);
void leo_test_dispatch_reset(void) { count=0; }
uint32_t leo_test_dispatch_count(void) { return count; }
int leo_test_dispatch_get(uint32_t index, test_dispatch *out)
{
    if (!out || index>=count) return -1;
    *out=records[index];
    return 0;
}
int __wrap_leo_probe_publish_held(leo_probe_pool *pool, uint32_t slot,
    const leo_probe_request *request)
{
    int result=__real_leo_probe_publish_held(pool,slot,request);
    if (!result) {
        struct timespec now;
        if (count>=2500 || clock_gettime(CLOCK_MONOTONIC,&now)) return -1;
        records[count++]=(test_dispatch){request->visit,request->valid_end,
            (uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec,
            request->channel-1+4*request->edge,0};
    }
    return result;
}
