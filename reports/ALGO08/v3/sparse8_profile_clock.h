#ifndef SPARSE8_PROFILE_CLOCK_H
#define SPARSE8_PROFILE_CLOCK_H
#include <stdint.h>

enum sparse8_stage {
    s_input, s_fir, s_modes, s_lag, s_carrier, s_seed, s_bank, s_confirm, s_load, s_verify, s_other, s_count
};

void sparse8_begin(void);
void sparse8_mark(enum sparse8_stage stage);
void sparse8_enable(int enabled);
void sparse8_collect(uint64_t clocks[s_count]);

#ifdef SPARSE8_CLOCK_IMPLEMENTATION
#include <stdlib.h>
#include <string.h>
#include <time.h>

static _Thread_local uint64_t previous;
static _Thread_local uint64_t clocks[s_count];
static _Thread_local int enabled;

static uint64_t cpu_time(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now) != 0) abort();
    return (uint64_t)now.tv_sec * 1000000000u + now.tv_nsec;
}

void sparse8_enable(int active) { enabled = active; }

void sparse8_begin(void)
{
    memset(clocks, 0, sizeof clocks);
    if (enabled) previous = cpu_time();
}

void sparse8_mark(enum sparse8_stage stage)
{
    if (!enabled) return;
    uint64_t total = cpu_time();
    clocks[stage] += total - previous;
    previous = total;
}

void sparse8_collect(uint64_t out[s_count]) { memcpy(out, clocks, sizeof clocks); }
#endif
#endif
