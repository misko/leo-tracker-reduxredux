#ifndef LEO_RECEIVER_DIRECTED_H
#define LEO_RECEIVER_DIRECTED_H

#include <stdint.h>
#include "portable_verifier.h"
#include "timing_first_receiver.h"

enum { directed_cap = 4 };
typedef struct {
    int epoch, sample;
    double coarse_epoch, offset, hz;
} DirectedSeed;

typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} DirectedFactor;

typedef struct {
    TimingFirstResult timing;
    int sample;
} DirectedTrace;

typedef struct {
    uint64_t refine_ns, gate_ns, cancel_ns, load_ns, verify_ns;
    unsigned gates, cancellations, verifies;
} DirectedCost;

enum {
    directed_decode, directed_refine, directed_fixed_exact, directed_fixed_guard,
    directed_full_load = 8
};

int directed_timing_trace(DirectedTrace *);
void directed_timing_input(TimingFirst *, const int16_t *, int);
int directed_timing_gate(TimingFirst *, const int16_t *, int, int, double);
int directed_timing_bank(TimingFirst *, const DirectedSeed *, int, double, double, double (*)[4]);
int directed_timing_cancel(TimingFirst *, const float *, float *, double, double);
int directed_load_apertures(PortableVerifier *, const int16_t *, unsigned, const unsigned *, int);
int directed_verify_fixed(PortableVerifier *, unsigned, double, double, int, PortableVerifierResult *);
int portable_verifier_factor(PortableVerifier *, unsigned, PortableVerifierResult *);

#endif
