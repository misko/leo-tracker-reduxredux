#include "two_carrier_receiver.h"
#include "pilot_cancel.h"
#include "portable_verifier.h"
#include "timing_first_receiver.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { period = 13333, samples = 200000, thirds = 40000 };
struct TwoCarrierReceiver {
    TimingFirst *timing;
    PortableVerifier *verify;
    PortableFineComplex true_pilot[period], rolled[period];
    float synthesis[2 * thirds], rotated[2 * thirds];
    int16_t residual[4 * samples];
};

TwoCarrierReceiver *two_carrier_create(const float *asset) {
    if (!asset) return NULL;
    TwoCarrierReceiver *r = calloc(1, sizeof(*r));
    if (!r) return NULL;
    for (int j = 0; j < period; ++j) {
        const float *a = asset + 2 * j, *b = a + 2 * period;
        r->true_pilot[j] = (PortableFineComplex){a[0], a[1]};
        r->rolled[j] = (PortableFineComplex){b[0], b[1]};
    }
    memcpy(r->synthesis, asset + 4 * period + 81, sizeof(r->synthesis));
    r->timing = timing_first_create(4, asset, asset + 4 * period);
    r->verify = portable_verifier_create(r->true_pilot, r->rolled);
    if (!r->timing || !r->verify) {
        two_carrier_free(r);
        return NULL;
    }
    return r;
}

void two_carrier_free(TwoCarrierReceiver *r) {
    if (r) {
        timing_first_free(r->timing);
        portable_verifier_free(r->verify);
        free(r);
    }
}

size_t two_carrier_bytes(const TwoCarrierReceiver *r) {
    return r ? sizeof(*r) + timing_first_bytes(r->timing) + portable_verifier_workspace_bytes() : 0;
}

static int same_peak(double e1, double f1, double e2, double f2) {
    return fabs(remainder(e1 - e2, (double)period)) <= 2. && fabs(f1 - f2) <= 1000.;
}

typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} ScanFactor;

int portable_verifier_factor(PortableVerifier *, unsigned, PortableVerifierResult *);

static int measure(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                   double lo, double hi, TwoCarrierPeak out[2], ScanFactor *factors) {
    if (!r || !out) return -1;
    TimingFirstResult p[2];
    if (timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])) return -1;
    if (!p[0].confirmation) return 0;
    if (pilot_cancel(iq, r->residual, lane, r->synthesis, r->rotated, p[0].epoch, p[0].hz) ||
        timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]) ||
        portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;
    int count = 0;
    for (int i = 0; i < 2; ++i) {
        if (!p[i].confirmation ||
            (i && same_peak(p[0].epoch, p[0].hz, p[1].epoch, p[1].hz))) continue;
        unsigned integer = (unsigned)nearbyint(p[i].epoch) % period;
        PortableVerifierResult v = {.acquired_hz = p[i].hz};
        if (portable_verifier_factor(r->verify, integer, &v)) return -1;
        if (!(v.flags & PORTABLE_VERIFIER_FRACTIONAL_GATE)) continue;
        double e = fmod(integer + v.offset_samples + period, period);
        double f = p[i].hz + v.fractional_residual_hz;
        if (!same_peak(p[i].epoch, p[i].hz, e, f) ||
            (count && same_peak(out[0].epoch, out[0].hz, e, f))) continue;
        if (factors) factors[count] = (ScanFactor){i, (int)integer, v.offset_samples, f,
                                                   v.fractional_exact, v.fractional_control};
        out[count++] = (TwoCarrierPeak){e, f, v.fractional_exact - v.fractional_control,
                                       i, p[i].confirmation};
    }
    if (count == 2 && out[1].margin > out[0].margin) {
        TwoCarrierPeak t = out[0];
        out[0] = out[1];
        out[1] = t;
        if (factors) {
            ScanFactor swap = factors[0];
            factors[0] = factors[1];
            factors[1] = swap;
        }
    }
    return count;
}

int two_carrier_detect(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                       double lo, double hi, TwoCarrierPeak out[2]) {
    return measure(r, iq, lane, lo, hi, out, NULL);
}

int cancellation_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                         double lo, double hi, ScanFactor out[2]) {
    TwoCarrierPeak peaks[2];
    return out ? measure(r, iq, lane, lo, hi, peaks, out) : -1;
}
