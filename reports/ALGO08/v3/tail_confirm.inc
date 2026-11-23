/* This experiment is compiled into the pinned portable verifier source. */
enum { tail_first = 9, tail_frames = 5, tail_halo = 40, prefix_samples = 120000 };

static double zero_ordinate(const GlrtComplex *values) {
    double power = 0., norm = 0.;
    for (int frame = 0; frame < tail_frames; ++frame) {
        double re = 0., im = 0., magnitude = 0.;
        for (int symbol = 0; symbol < 64; ++symbol) {
            const GlrtComplex value = values[frame*64 + symbol];
            re += value.re;
            im += value.im;
            magnitude += hypot(value.re, value.im);
        }
        power += re*re + im*im;
        norm += magnitude*magnitude;
    }
    return norm > 0. ? power/norm : 0.;
}

int tail_confirm(PortableVerifier *w, const int16_t *iq, unsigned lane, unsigned epoch,
                 double offset, double cfo, double scores[2]) {
    if (!w || !iq || !scores || lane > 1 || epoch >= n ||
        !isfinite(offset) || fabs(offset) > 1.5 || !isfinite(cfo)) return -1;
    int32_t starts[tail_frames];
    for (int f = 0; f < tail_frames; ++f) {
        starts[f] = frame_start(epoch, f + tail_first);
        const int lo = (int)floor(starts[f] + first + offset) - 7 - tail_halo;
        const int hi = (int)floor(starts[f] + stop - 1 + offset) + 8 + tail_halo;
        if (lo < prefix_samples || hi >= samples) return -1;
        for (int k = lo; k <= hi; ++k) {
            w->iq.fine[k] = (PortableFineSample){iq[4*k + 2*lane], iq[4*k + 2*lane + 1]};
        }
    }
    if (fabs(offset - nearbyint(offset)) <= 1e-12) {
        for (int f = 0; f < tail_frames; ++f) starts[f] += first + (int)nearbyint(offset);
        prepare_integer_rotation(w, cfo);
        const int32_t zero = 0;
        correlated_integer(w->iq.glrt, starts, 1, tail_frames, &zero, w->glrt_rotation,
                           w->glrt_exact, w->glrt_control, w->correlations[0], w->correlations[1]);
    } else if (absolute_fractional_correlations(w, tail_frames, starts, cfo, offset)) {
        return -1;
    }
    scores[0] = zero_ordinate(w->correlations[0]);
    scores[1] = zero_ordinate(w->correlations[1]);
    return 0;
}
