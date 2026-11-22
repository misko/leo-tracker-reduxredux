#ifndef LEO_TIMING_FIRST_RECEIVER_H
#define LEO_TIMING_FIRST_RECEIVER_H

#include <stddef.h>
#include <stdint.h>

typedef struct TimingFirst TimingFirst;
typedef struct {
    double epoch, hz, score;
    int confirmation; /* 0 withheld, 1 later symbols, 2 seven early frame pairs */
} TimingFirstResult;

/* The pilot is 13,333 interleaved complex float32 samples. The nominal mode uses
   81 symmetric quarter-rate FIR coefficients. The physical-band mode uses stride 1. */
TimingFirst *timing_first_create(int stride, const float *pilot, const float *fir);
void timing_first_free(TimingFirst *receiver);
size_t timing_first_bytes(const TimingFirst *receiver);
int timing_first_detect(TimingFirst *receiver, const int16_t *stereo_iq, int lane, double low_hz,
                        double high_hz, TimingFirstResult *out);

#endif
