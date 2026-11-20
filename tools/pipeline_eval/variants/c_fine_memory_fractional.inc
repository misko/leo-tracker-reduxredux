/* Only one fractional frame is live. The previous rounded fraction is carried
 * forward, so both weight rounding and ordered per-symbol reductions match. */
static int fractional_correlations(PortableVerifier *w, int frames, const int32_t *starts,
                                   double cfo, double offset) {
    double old_fraction = NAN;
    int row = -1;
    for (int f = 0; f < frames; ++f) {
        for (int k = 0; k < aperture; ++k) {
            const double position = starts[f] + first+k + offset;
            const int base = (int)position;
            const double fraction = position - base;
            w->indices[k] = base - 7;
            if (fraction != old_fraction) {
                double norm = 0;
                if (++row >= rounded_weight_rows) return -1;
                for (int t = 0; t < 16; ++t) {
                    const double distance = fraction - (t - 7);
                    w->weights[row][t] = sinc(distance)*sinc(distance/8);
                    norm += w->weights[row][t];
                }
                for (int t = 0; t < 16; ++t) w->weights[row][t] /= norm;
                old_fraction = fraction;
            }
            w->weight_row[k] = row;
            const PortableFineComplex z = rotate(-tau*cfo*position/rate);
            w->fractional_rotation[k] = (GlrtComplex){z.r,z.i};
        }
        correlated_fractional(w->iq.glrt, w->indices, 1, w->weight_row, &w->weights[0][0],
                              w->fractional_rotation, w->glrt_exact, w->glrt_control,
                              w->correlations[0]+f*64, w->correlations[1]+f*64);
    }
    return 0;
}
