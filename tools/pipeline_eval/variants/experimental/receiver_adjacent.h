#ifndef LEO_EXPERIMENTAL_RECEIVER_ADJACENT_H
#define LEO_EXPERIMENTAL_RECEIVER_ADJACENT_H

#include "timing_first_receiver.h"

typedef struct scout_context scout_context;
typedef float DifferentialFilter[2];
typedef struct {
    unsigned scouts, fallback[2], confirmed[2];
} AdjacentStats;

scout_context *leo_differential_scout_create(void);
void leo_differential_scout_destroy(scout_context *);
void leo_differential_scout_lane(scout_context *, const int16_t *, int,
                                const DifferentialFilter *, const double *, double *);

int timing_adjacent_configure(TimingFirst *, const DifferentialFilter *, const double *);
void timing_adjacent_mode(TimingFirst *, AdjacentStats *, int);

#endif
