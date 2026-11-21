/* Copy the scores from the cancellation receiver's two existing fractional
   verifier calls into the native position input. No waveform is rescored. */
#include "../variants/two_carrier_receiver.h"
#include "../variants/portable_verifier.h"
#include <math.h>

typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} ScanFactor;

typedef struct {
    ScanFactor calls[2];
    unsigned count;
} FactorTrace;

static _Thread_local FactorTrace *active_trace;
int __real_portable_verifier_glrt(PortableVerifier *, unsigned, PortableVerifierResult *);

int __wrap_portable_verifier_glrt(PortableVerifier *receiver, unsigned epoch,
                                  PortableVerifierResult *result) {
    int status = __real_portable_verifier_glrt(receiver, epoch, result);
    if (active_trace && !status && active_trace->count < 2) {
        unsigned i = active_trace->count++;
        active_trace->calls[i] = (ScanFactor){(int)i, (int)epoch, result->offset_samples,
            result->acquired_hz + result->fractional_residual_hz,
            result->fractional_exact, result->fractional_control};
    }
    return status;
}

int cancellation_factors(TwoCarrierReceiver *receiver, const int16_t *iq, int lane,
                         double lo, double hi, ScanFactor out[2]) {
    if (!out || active_trace) return -1;
    FactorTrace trace = {0};
    TwoCarrierPeak peaks[2];
    active_trace = &trace;
    int count = two_carrier_detect(receiver, iq, lane, lo, hi, peaks);
    active_trace = NULL;
    for (int j = 0; j < count; ++j) {
        int rank = peaks[j].rank;
        if (rank < 0 || (unsigned)rank >= trace.count) return -1;
        ScanFactor v = trace.calls[rank];
        if (v.hz != peaks[j].hz || v.exact - v.control != peaks[j].margin ||
            fabs(remainder(v.integer + v.offset - peaks[j].epoch, 13333.)) > 1e-7)
            return -1;
        out[j] = v;
    }
    return count;
}
