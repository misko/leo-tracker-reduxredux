#ifndef LEO_EXPERIMENTAL_RECEIVER_PROJECTION_H
#define LEO_EXPERIMENTAL_RECEIVER_PROJECTION_H

#include "timing_first_receiver.h"

enum { projection_seeds = 4 };
typedef struct {
    double epoch, hz;
} ProjectedSeed;
typedef struct {
    unsigned seed_count, attempted, zero;
    ProjectedSeed seeds[projection_seeds];
} ProjectionTrace;
typedef struct {
    ProjectionTrace scan[2];
    unsigned fallback;
} ProjectionVisit;

int projection_detect(TimingFirst *, const int16_t *, const int16_t *, int, double, double,
                      TimingFirstResult *, ProjectionTrace *);

#endif
