#include <stdint.h>
#include <time.h>

static _Thread_local uint64_t rank_cost[2];

static uint64_t rank_now(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t)) return 0;
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

void short_rank_trace_take(uint64_t out[2])
{
    for (int i = 0; i < 2; ++i) {
        out[i] = rank_cost[i];
        rank_cost[i] = 0;
    }
}
