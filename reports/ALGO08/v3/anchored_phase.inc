/* A distinct experimental receiver. Keep absolute positions and re-anchor every 32 taps. */
#include <fenv.h>

enum { anchor_stride = 32, audit_capacity = 8 };

typedef struct {
    unsigned epoch, flags;
    double frequency, offset, residual, exact, control;
} RotationAudit;

static _Thread_local RotationAudit audit[audit_capacity];
static _Thread_local unsigned audit_count;
static _Thread_local uint64_t phase_count[2];

int anchored_take_audit(RotationAudit out[audit_capacity], uint64_t counts[2]) {
    unsigned count = audit_count;
    if (count > audit_capacity) return -1;
    memcpy(out, audit, count * sizeof(*out));
    memcpy(counts, phase_count, sizeof(phase_count));
    audit_count = 0;
    phase_count[0] = phase_count[1] = 0;
    return (int)count;
}

static void track_rotation(unsigned epoch, const PortableVerifierResult *out) {
    if (audit_count < audit_capacity) {
        audit[audit_count] = (RotationAudit){epoch, out->flags, out->acquired_hz, out->offset_samples,
            out->fractional_residual_hz, out->fractional_exact, out->fractional_control};
    }
    ++audit_count;
}

static int anchored_correlations(PortableVerifier *, int, const int32_t *, double, double, double *);

/* Use the prior conservative normalized-spectrum enclosure with a per-block
   recurrence allowance. An inconclusive enclosure takes the original exact path. */
static int anchored_decision(double e, double c, double egap, double cgap, double er, double cr) {
    const double radius = er + cr;
    const double margin = e - c;
    return egap > 2.*er && cgap > 2.*cr && fabs(margin - gate) > radius && fabs(margin - .1) > radius;
}

int anchored_guard_fixture(double e, double c, double egap, double cgap, double er, double cr) {
    return anchored_decision(e, c, egap, cgap, er, cr);
}

static int anchored_fractional(PortableVerifier *w, int frames, const int32_t *starts,
                               double cfo, double offset, double *exact_out,
                               double *control_out, int *winner, unsigned *flags) {
    ++phase_count[0];
    double weight_mass;
    if (fegetround() != FE_TONEAREST || anchored_correlations(w, frames, starts, cfo, offset, &weight_mass))
        return 0;
    double exact_l1 = 0., control_l1 = 0.;
    for (int k = 0; k < aperture; ++k) {
        exact_l1 += fabs(w->glrt_exact[k].re) + fabs(w->glrt_exact[k].im);
        control_l1 += fabs(w->glrt_control[k].re) + fabs(w->glrt_control[k].im);
    }
    unsigned trial_flags = 0;
    int other;
    double ec = 0., cc = 0., egap = 0., cgap = 0.;
    double exact = glrt_spectrum_details(w, w->correlations[0], frames, winner, &trial_flags, &ec, &egap);
    double control = glrt_spectrum_details(w, w->correlations[1], frames, &other, &trial_flags, &cc, &cgap);
    const double rotation_error = 128.*DBL_EPSILON*(anchor_stride + 1. + tau*fabs(cfo)*samples/rate);
    const double raw_error = rotation_error * 65536. * weight_mass;
    const double er = spectrum_radius(ec, frames, raw_error*exact_l1);
    const double cr = spectrum_radius(cc, frames, raw_error*control_l1);
    if (!anchored_decision(exact, control, egap, cgap, er, cr)) return 0;
    *exact_out = exact;
    *control_out = control;
    *flags |= trial_flags;
    w->phase_margin_radius = er + cr;
    ++phase_count[1];
    return 1;
}

/* The independent CFO measurement uses exact fallback near its original gates.
   Low coherence also falls back before comparing any continuous diagnostics. */
static int tail_needs_exact(const double out[8]) {
    for (int i = 0; i < 8; ++i)
        if (!isfinite(out[i])) return 1;
    const double coherence = fmin(out[3], out[4]);
    return coherence < .5 || fabs(coherence-.70) < 1e-7 ||
           fabs((out[5]-out[6])-.025) < 1e-7 || fabs(fabs(out[0])-250.) < .001 ||
           fabs(fabs(out[2]-out[1])-400.) < .002;
}

int anchored_tail_guard_fixture(const double out[8]) {
    return tail_needs_exact(out);
}
