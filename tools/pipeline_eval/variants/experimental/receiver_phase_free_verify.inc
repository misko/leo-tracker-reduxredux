void correlated_fractional_mixed(const GlrtSample *, const int32_t *, const int32_t *,
                                 const double *, const GlrtComplex *, const GlrtComplex *,
                                 GlrtComplex *, GlrtComplex *);

static _Thread_local uint64_t phase_attempts, phase_accepted, phase_order_retries;

void experimental_phase_free_stats(uint64_t out[3], int reset)
{
    out[0] = phase_attempts;
    out[1] = phase_accepted;
    out[2] = phase_order_retries;
    if (reset) phase_attempts = phase_accepted = phase_order_retries = 0;
}

double portable_verifier_margin_radius(const PortableVerifier *w)
{
    return w->phase_margin_radius;
}

void portable_verifier_margin_order_retry(void)
{
    ++phase_order_retries;
}

/* Bound the normalized spectrum using the L1 perturbation in each frame.
 * 32768 bounds either CI16 component; two bounds the complex magnitude. */
static double spectrum_radius(double ceiling, int frames, double error)
{
    if (!(ceiling > 0.) || !isfinite(ceiling)) return INFINITY;
    double amplitude = error * sqrt(frames / ceiling);
    double power = (2. + amplitude) * amplitude;
    return power < .25 ? 4. * power / (1. - power) + 1e-11 : INFINITY;
}

/* The omitted absolute time origin gives each frame a constant phase, which
 * cancels in the squared spectrum and its normalization. Keep the original
 * absolute rounded fractional positions for all Lanczos reads and weights. */
static int phase_free_fractional(PortableVerifier *w, int frames, const int32_t *starts,
                                 double cfo, double offset, double *exact_out,
                                 double *control_out, int *winner, unsigned *flags)
{
    ++phase_attempts;
    GlrtComplex exact[aperture], control[aperture];
    double exact_l1 = 0., control_l1 = 0.;
    for (int k = 0; k < aperture; ++k) {
        PortableFineComplex p = rotate(-tau * cfo * (first + k + offset) / rate);
        GlrtComplex a = w->glrt_exact[k], b = w->glrt_control[k];
        exact[k] = (GlrtComplex){a.re * p.r - a.im * p.i, a.re * p.i + a.im * p.r};
        control[k] = (GlrtComplex){b.re * p.r - b.im * p.i, b.re * p.i + b.im * p.r};
        exact_l1 += fabs(a.re) + fabs(a.im);
        control_l1 += fabs(b.re) + fabs(b.im);
    }
    double old_fraction = NAN, max_weight = 0.;
    int row = -1;
    for (int f = 0; f < frames; ++f) {
        for (int k = 0; k < aperture; ++k) {
            const double position = starts[f] + first + k + offset;
            const int base = (int)position;
            const double fraction = position - base;
            w->indices[k] = base - 7;
            if (fraction != old_fraction) {
                double norm = 0., mass = 0.;
                if (++row >= rounded_weight_rows) return 0;
                for (int t = 0; t < 16; ++t) {
                    double distance = fraction - (t - 7);
                    w->weights[row][t] = sinc(distance) * sinc(distance / 8);
                    norm += w->weights[row][t];
                }
                for (int t = 0; t < 16; ++t) {
                    w->weights[row][t] /= norm;
                    mass += fabs(w->weights[row][t]);
                }
                max_weight = fmax(max_weight, mass);
                old_fraction = fraction;
            }
            w->weight_row[k] = row;
        }
        correlated_fractional_mixed(w->iq.glrt, w->indices, w->weight_row, &w->weights[0][0],
                                    exact, control, w->correlations[0] + f * 64,
                                    w->correlations[1] + f * 64);
    }
    int other;
    unsigned trial_flags = 0;
    double ec = 0., cc = 0., egap = 0., cgap = 0.;
    double e = glrt_spectrum_details(w, w->correlations[0], frames, winner, &trial_flags, &ec, &egap);
    double c = glrt_spectrum_details(w, w->correlations[1], frames, &other, &trial_flags, &cc, &cgap);
    /* Allow absolute and relative phase argument rounding, sin/cos, complex
     * products and the symbol accumulation before accounting for FFT power. */
    double roundoff = 128. * DBL_EPSILON * (1. + tau * fabs(cfo) * samples / rate);
    double raw_error = roundoff * 65536. * max_weight;
    double er = spectrum_radius(ec, frames, raw_error * exact_l1);
    double cr = spectrum_radius(cc, frames, raw_error * control_l1);
    double margin = e - c, radius = er + cr;
    /* ALGO08v2's factor gate and the published strong-margin count. */
    if (!(egap > 2. * er && cgap > 2. * cr &&
          fabs(margin - gate) > radius && fabs(margin - .1) > radius)) return 0;

    *exact_out = e;
    *control_out = c;
    w->phase_margin_radius = radius;
    *flags |= trial_flags;
    ++phase_accepted;
    return 1;
}
