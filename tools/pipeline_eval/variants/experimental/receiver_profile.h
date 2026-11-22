#ifndef LEO_RECEIVER_PROFILE_H
#define LEO_RECEIVER_PROFILE_H

#include <stdint.h>
#include <time.h>

typedef enum {
    PROFILE_MEASURE, PROFILE_TIMING, PROFILE_INPUT, PROFILE_DECIMATE, PROFILE_MODES,
    PROFILE_TIME_SEARCH, PROFILE_CARRIER_SEARCH, PROFILE_REFINE, PROFILE_GATE,
    PROFILE_CANCEL, PROFILE_VERIFY_LOAD, PROFILE_VERIFY, PROFILE_COUNT
} ProfileStage;

typedef struct { uint64_t calls, ns; } ProfileStat;
typedef struct { ProfileStage stage; uint64_t start; } ProfileTimer;
extern _Thread_local ProfileStat receiver_stats[PROFILE_COUNT];

static inline uint64_t receiver_clock(void) {
    struct timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static inline void receiver_stop(ProfileTimer *timer) {
    ProfileStat *record = receiver_stats + timer->stage;
    ++record->calls;
    record->ns += receiver_clock() - timer->start;
}

#define PROFILE(stage) \
    ProfileTimer timer __attribute__((cleanup(receiver_stop))) = {PROFILE_##stage, receiver_clock()}

#endif
