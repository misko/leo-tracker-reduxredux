#include "pilot_cancel.h"
#include "portable_verifier.h"
#include "timing_first_receiver.h"
#include "two_carrier_receiver.h"

#include <assert.h>
#include <stdbool.h>

typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} ScanFactor;

int cancellation_factors(TwoCarrierReceiver *, const int16_t *, int, double, double, ScanFactor *);
int cancellation_primary_factors(TwoCarrierReceiver *, const int16_t *, int, double, double,
                                 ScanFactor *);

static const int16_t raw_iq[1];
static bool scout_raw = true, verify_raw = true;
static unsigned raw_searches, residual_searches, cancellations, verifications;

struct TimingFirst { int unused; };
struct PortableVerifier { int unused; };
static TimingFirst timing;
static PortableVerifier verifier;

TimingFirst *timing_first_create(int stride, const float *pilot, const float *fir) {
    (void)stride; (void)pilot; (void)fir;
    return &timing;
}
void timing_first_free(TimingFirst *r) { (void)r; }
size_t timing_first_bytes(const TimingFirst *r) { (void)r; return 0; }

int timing_first_detect(TimingFirst *r, const int16_t *iq, int lane, double lo, double hi,
                        TimingFirstResult *out) {
    (void)r; (void)lane; (void)lo; (void)hi;
    if (iq == raw_iq) {
        raw_searches++;
        *out = (TimingFirstResult){100., 100000., 0., scout_raw ? 2 : 0};
    } else {
        residual_searches++;
        *out = (TimingFirstResult){500., -100000., 0., 1};
    }
    return 0;
}

int pilot_cancel(const int16_t *input, int16_t *output, int lane, const float *pilot,
                 float *scratch, double epoch, double carrier_hz) {
    (void)output; (void)lane; (void)pilot; (void)scratch; (void)epoch; (void)carrier_hz;
    assert(input == raw_iq);
    cancellations++;
    return 0;
}

PortableVerifier *portable_verifier_create(const PortableFineComplex *actual,
                                          const PortableFineComplex *control) {
    (void)actual; (void)control;
    return &verifier;
}
void portable_verifier_free(PortableVerifier *v) { (void)v; }
size_t portable_verifier_workspace_bytes(void) { return 0; }

int portable_verifier_load(PortableVerifier *v, const int16_t *iq, unsigned lane) {
    (void)v; (void)lane;
    assert(iq == raw_iq);
    return 0;
}

int portable_verifier_factor(PortableVerifier *v, unsigned epoch, PortableVerifierResult *r) {
    (void)v;
    verifications++;
    assert(epoch == 100 || epoch == 500);
    r->flags = epoch == 500 || verify_raw ? PORTABLE_VERIFIER_FRACTIONAL_GATE : 0;
    r->offset_samples = .25;
    r->fractional_residual_hz = 75.;
    r->fractional_exact = epoch == 500 ? .8 : .3;
    r->fractional_control = .1;
    return 0;
}

int main(void) {
    static const float asset[133413];
    TwoCarrierReceiver *receiver=two_carrier_create(asset);
    assert(receiver);
    ScanFactor full[2], raw[2];
    assert(cancellation_factors(receiver,raw_iq,0,-800000,800000,full)==2);
    assert(full[0].rank==1 && full[1].rank==0);
    assert(cancellation_primary_factors(receiver,raw_iq,0,-800000,800000,raw)==1);
    assert(raw[0].rank==0 && raw[0].integer==full[1].integer && raw[0].offset==full[1].offset);
    assert(raw[0].hz==full[1].hz && raw[0].exact==full[1].exact && raw[0].control==full[1].control);
    assert(raw_searches==2 && residual_searches==1 && cancellations==1 && verifications==3);

    verify_raw=false;
    assert(cancellation_factors(receiver,raw_iq,0,-800000,800000,full)==1);
    assert(full[0].rank==1);
    assert(cancellation_primary_factors(receiver,raw_iq,0,-800000,800000,raw)==0);
    assert(raw_searches==4 && residual_searches==2 && cancellations==2 && verifications==6);

    scout_raw=false;
    assert(cancellation_factors(receiver,raw_iq,0,-800000,800000,full)==0);
    assert(cancellation_primary_factors(receiver,raw_iq,0,-800000,800000,raw)==0);
    assert(raw_searches==6 && residual_searches==2 && cancellations==2 && verifications==6);
    two_carrier_free(receiver);
    return 0;
}
