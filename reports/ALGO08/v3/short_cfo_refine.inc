/* Linked against the checked portable verifier and its original interpolation. */
enum { short_limit = 120000, delay_symbols = 32 };

typedef struct { double re, im, scale; } DelayProduct;

static void accumulate(DelayProduct *delay, const GlrtComplex *values) {
    GlrtComplex blocks[8] = {{0., 0.}};
    for (int k = 0; k < 64; ++k) {
        blocks[k/8].re += values[k].re;
        blocks[k/8].im += values[k].im;
    }
    for (int k = 0; k < 4; ++k) {
        const GlrtComplex a = blocks[k], b = blocks[k+4];
        delay->re += a.re*b.re + a.im*b.im;
        delay->im += a.re*b.im - a.im*b.re;
        delay->scale += hypot(a.re, a.im)*hypot(b.re, b.im);
    }
}

static double residual_hz(DelayProduct product) {
    return atan2(product.im, product.re)*rate/(tau*delay_symbols*taps);
}

static double coherent(DelayProduct product) {
    return product.scale > 0. ? hypot(product.re, product.im)/product.scale : 0.;
}

static void score_frame(const GlrtComplex *values, double *power, double *ceiling) {
    double re = 0., im = 0., norm = 0.;
    for (int k = 0; k < 64; ++k) {
        re += values[k].re;
        im += values[k].im;
        norm += hypot(values[k].re, values[k].im);
    }
    *power += re*re + im*im;
    *ceiling += norm*norm;
}

int short_cfo_refine(PortableVerifier *w, const int16_t *iq, unsigned lane, unsigned epoch,
                     double offset, double cfo, double out[8]) {
    if (!w || !iq || !out || lane > 1 || epoch >= n || !isfinite(cfo) || fabs(cfo) > 5e6 ||
        !isfinite(offset) || fabs(offset) > 1.5) return -1;
    const int integer = fabs(offset - nearbyint(offset)) <= 1e-12;
    int32_t starts[max_frames];
    int group[max_frames], frames = 0;
    for (int frame = 0; frame < max_frames; ++frame) {
        const int start = frame_start(epoch, frame);
        const int lo = (int)floor(start+first+offset) - (integer ? 0 : 7);
        const int hi = (int)floor(start+stop-1+offset) + (integer ? 0 : 8);
        if (lo < 0 || hi >= samples) break;
        starts[frames] = start;
        group[frames++] = hi < short_limit ? 0 : lo >= short_limit ? 1 : -1;
    }
    if (!frames || portable_verifier_load(w, iq, lane)) return -1;
    if (integer) {
        for (int f = 0; f < frames; ++f) starts[f] += first + (int)nearbyint(offset);
        prepare_integer_rotation(w, cfo);
        const int32_t zero = 0;
        correlated_integer(w->iq.glrt, starts, 1, frames, &zero, w->glrt_rotation,
                           w->glrt_exact, w->glrt_control, w->correlations[0], w->correlations[1]);
    } else if (absolute_fractional_correlations(w, frames, starts, cfo, offset)) {
        return -1;
    }
    DelayProduct all = {0., 0., 0.}, parts[2] = {{0., 0., 0.}};
    double power[2] = {0., 0.}, ceiling[2] = {0., 0.};
    int tail_frames = 0;
    for (int f = 0; f < frames; ++f) {
        const GlrtComplex *row = w->correlations[0] + 64*f;
        accumulate(&all, row);
        if (group[f] >= 0) accumulate(&parts[group[f]], row);
        if (group[f] == 1) {
            ++tail_frames;
            score_frame(row, power, ceiling);
            score_frame(w->correlations[1] + 64*f, power+1, ceiling+1);
        }
    }
    out[0] = residual_hz(all);
    out[1] = residual_hz(parts[0]);
    out[2] = residual_hz(parts[1]);
    out[3] = coherent(parts[0]);
    out[4] = coherent(parts[1]);
    out[5] = ceiling[0] > 0. ? power[0]/ceiling[0] : 0.;
    out[6] = ceiling[1] > 0. ? power[1]/ceiling[1] : 0.;
    out[7] = (double)tail_frames;
    return 0;
}
