#ifndef LEO_TWO_CARRIER_RECEIVER_H
#define LEO_TWO_CARRIER_RECEIVER_H

#include <stddef.h>
#include <stdint.h>

typedef struct TwoCarrierReceiver TwoCarrierReceiver;
typedef struct {
    double epoch, hz, margin;
    int rank, confirmation;
} TwoCarrierPeak;

enum { TWO_CARRIER_ASSET_FLOATS = 4 * 13333 + 81 + 2 * 40000 };
/* The asset contains 10 MS/s complex pilots (true and rolled), 81 real FIR taps,
   and a 30 MS/s complex pilot. The receiver takes its own copy where needed. */
TwoCarrierReceiver *two_carrier_create(const float *asset);
void two_carrier_free(TwoCarrierReceiver *receiver);
size_t two_carrier_bytes(const TwoCarrierReceiver *receiver);
/* Returns -1 for an invalid input, otherwise 0..2 original-I/Q-verified peaks,
   ordered by decreasing fractional margin, then extraction rank. */
int two_carrier_detect(TwoCarrierReceiver *receiver, const int16_t *stereo, int lane,
                       double lo, double hi, TwoCarrierPeak peaks[2]);

#endif
