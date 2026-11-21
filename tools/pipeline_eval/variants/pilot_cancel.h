#ifndef LEO_PILOT_CANCEL_H
#define LEO_PILOT_CANCEL_H

#include <stdint.h>

/* pilot and scratch hold 40,000 interleaved complex float32 samples at 30 MS/s.
   input and output are separate 20 ms stereo interleaved CI16 buffers at 10 MS/s. */
int pilot_cancel(const int16_t *input, int16_t *output, int lane, const float *pilot,
                 float *scratch, double epoch, double carrier_hz);

#endif
