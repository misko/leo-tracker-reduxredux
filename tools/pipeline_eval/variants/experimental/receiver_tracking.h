#ifndef LEO_EXPERIMENTAL_RECEIVER_TRACKING_H
#define LEO_EXPERIMENTAL_RECEIVER_TRACKING_H

#include "timing_first_receiver.h"

enum { max_tracking_hints = 2 };
typedef struct { int epoch; double hz; } TimingHint;
typedef struct {
    unsigned global_first, global_residual, short_first, short_residual, narrow_first, reacquire;
} TrackingStats;

int experimental_timing_detect(TimingFirst *, const int16_t *, int, double, double,
                               TimingFirstResult *, const TimingHint *, unsigned, int);

#endif
