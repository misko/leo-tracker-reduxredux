#ifndef LEO_EXPERIMENTAL_RESIDENT_CANCEL_H
#define LEO_EXPERIMENTAL_RESIDENT_CANCEL_H

#include "timing_first_receiver.h"

/* The argument holds a deinterleaved, unrotated signed-CI16 lane in float32. */
int pilot_cancel_resident(float *, const float *, float *, double, double);

/* Call immediately after the same workspace confirmed the primary scout. */
int timing_first_cancel_resident(TimingFirst *, const float *, float *, const TimingFirstResult *,
                                 double, double, TimingFirstResult *);

#endif
