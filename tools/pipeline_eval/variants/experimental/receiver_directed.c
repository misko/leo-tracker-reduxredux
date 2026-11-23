#define _POSIX_C_SOURCE 200809L
#include "receiver_directed.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { directed_period = 13333, synthesis_length = 2 * 40000 };

typedef struct {
    TimingFirst *timing;
    PortableVerifier *verify;
    PortableFineComplex exact[directed_period], rolled[directed_period];
    float synthesis[synthesis_length], rotation[synthesis_length];
} DirectedReceiver;

static uint64_t clock_ns(void) {
    struct timespec tick;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &tick);
    return (uint64_t)tick.tv_sec * UINT64_C(1000000000) + tick.tv_nsec;
}

DirectedReceiver *directed_create(const float *asset) {
    if (!asset) return NULL;
    DirectedReceiver *r = calloc(1, sizeof(*r));
    if (!r) return NULL;
    for (int i = 0; i < directed_period; ++i) {
        r->exact[i] = (PortableFineComplex){asset[2 * i], asset[2 * i + 1]};
        const float *b = asset + 2 * (directed_period + i);
        r->rolled[i] = (PortableFineComplex){b[0], b[1]};
    }
    memcpy(r->synthesis, asset + 4 * directed_period + 81, sizeof(r->synthesis));
    r->timing = timing_first_create(4, asset, asset + 4 * directed_period);
    r->verify = portable_verifier_create(r->exact, r->rolled);
    if (!r->timing || !r->verify) {
        timing_first_free(r->timing);
        portable_verifier_free(r->verify);
        free(r);
        return NULL;
    }
    return r;
}

void directed_free(DirectedReceiver *r) {
    if (!r) return;
    timing_first_free(r->timing);
    portable_verifier_free(r->verify);
    free(r);
}

static int same(double a, double ahz, double b, double bhz) {
    return fabs(remainder(a - b, directed_period)) <= 2. && fabs(ahz - bhz) <= 1000.;
}

typedef struct {
    DirectedSeed seed;
    double refine_epoch;
    int confirmation;
} DirectedPeak;

static int find_peak(DirectedReceiver *r, const int16_t *iq, int lane, const DirectedSeed *seeds,
                     int count, double lo, double hi, int mode, DirectedCost *cost, DirectedPeak *p) {
    if (!count) return 0;
    double refinements[directed_cap][4];
    if (mode == directed_refine) {
        uint64_t begin = clock_ns();
        if (iq) directed_timing_input(r->timing, iq, lane);
        if (directed_timing_bank(r->timing, seeds, count, lo, hi, refinements)) return -1;
        cost->refine_ns += clock_ns() - begin;
        iq = NULL;
    }
    for (int i = 0; i < count; ++i) {
        DirectedSeed s = seeds[i];
        int sample = s.sample;
        double epoch = s.coarse_epoch;
        if (mode == directed_refine) {
            int best = 0;
            for (int j = 1; j < count; ++j)
                if (refinements[j][3] > refinements[best][3]) best = j;
            epoch = refinements[best][0];
            sample = (int)refinements[best][2];
            s = (DirectedSeed){(int)nearbyint(epoch) % directed_period, sample, epoch, 0.,
                               refinements[best][1]};
            refinements[best][3] = -1.;
        }
        uint64_t begin = clock_ns();
        int confirm = directed_timing_gate(r->timing, iq, lane, sample, s.hz);
        cost->gate_ns += clock_ns() - begin;
        ++cost->gates;
        if (confirm) {
            *p = (DirectedPeak){s, epoch, confirm};
            return 1;
        }
    }
    return 0;
}

int directed_run(DirectedReceiver *r, const int16_t *iq, int lane, const DirectedSeed *seeds,
                 int count, double lo, double hi, int mode, DirectedFactor *factors, DirectedCost *cost) {
    int full_load = mode & directed_full_load;
    mode &= ~directed_full_load;
    if (!r || !iq || lane < 0 || lane > 1 || !seeds || !factors || !cost || count < 1 ||
        count > directed_cap || mode < directed_decode || mode > directed_fixed_guard || !(lo < hi))
        return -1;
    *cost = (DirectedCost){0};
    for (int i = 0; i < count; ++i)
        if (seeds[i].epoch < 0 || seeds[i].epoch >= directed_period ||
            seeds[i].sample < 0 || seeds[i].sample >= directed_period ||
            !isfinite(seeds[i].coarse_epoch) || seeds[i].coarse_epoch < 0. ||
            seeds[i].coarse_epoch >= directed_period ||
            !isfinite(seeds[i].offset) || fabs(seeds[i].offset) > 2. ||
            !(lo <= seeds[i].hz && seeds[i].hz <= hi))
            return -1;
    DirectedPeak peaks[2];
    int found = find_peak(r, iq, lane, seeds, count, lo, hi, mode, cost, peaks);
    if (found <= 0) return found;
    DirectedSeed remaining[directed_cap];
    int next = 0;
    for (int i = 0; i < count; ++i)
        if (!same(seeds[i].coarse_epoch, seeds[i].hz, peaks[0].refine_epoch, peaks[0].seed.hz))
            remaining[next++] = seeds[i];
    if (next) {
        uint64_t begin = clock_ns();
        if (mode != directed_refine)
            directed_timing_input(r->timing, iq, lane);
        if (directed_timing_cancel(r->timing, r->synthesis, r->rotation,
                                   peaks[0].refine_epoch, peaks[0].seed.hz))
            return -1;
        cost->cancel_ns = clock_ns() - begin;
        ++cost->cancellations;
        int residual = find_peak(r, NULL, lane, remaining, next, lo, hi, mode, cost, peaks + 1);
        if (residual < 0) return -1;
        found += residual;
    }
    uint64_t begin = clock_ns();
    unsigned epochs[2] = {(unsigned)peaks[0].seed.epoch, 0};
    if (found == 2) epochs[1] = (unsigned)peaks[1].seed.epoch;
    int loaded = full_load ? portable_verifier_load(r->verify, iq, (unsigned)lane)
                           : directed_load_apertures(r->verify, iq, (unsigned)lane, epochs, found);
    if (loaded) return -1;
    cost->load_ns = clock_ns() - begin;
    int accepted = 0;
    for (int i = 0; i < found; ++i) {
        DirectedSeed s = peaks[i].seed;
        PortableVerifierResult out = {.acquired_hz = s.hz};
        begin = clock_ns();
        int status = mode < directed_fixed_exact ? portable_verifier_factor(r->verify, s.epoch, &out) :
            directed_verify_fixed(r->verify, s.epoch, s.hz, s.offset, mode == directed_fixed_guard, &out);
        cost->verify_ns += clock_ns() - begin;
        ++cost->verifies;
        double hz = s.hz + out.fractional_residual_hz;
        double epoch = s.epoch + out.offset_samples;
        if (status) return -1;
        if (!(out.flags & PORTABLE_VERIFIER_FRACTIONAL_GATE) ||
            !same(peaks[i].refine_epoch, s.hz, epoch, hz) ||
            (accepted && same(factors[0].integer + factors[0].offset, factors[0].hz, epoch, hz))) continue;
        factors[accepted++] = (DirectedFactor){i, s.epoch, out.offset_samples, hz,
                                               out.fractional_exact, out.fractional_control};
    }
    if (accepted == 2 && factors[1].exact - factors[1].control > factors[0].exact - factors[0].control) {
        DirectedFactor t = factors[0];
        factors[0] = factors[1];
        factors[1] = t;
    }
    return accepted;
}
