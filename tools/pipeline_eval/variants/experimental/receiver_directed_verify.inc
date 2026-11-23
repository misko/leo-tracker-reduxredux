/* The factor scorer reads only the first 64 symbols per included frame.
   Pad for its five integer centers, signed fractional offset, Lanczos
   support and vector loads. Wrapped stencil centers use the ordinary load. */
int directed_load_apertures(PortableVerifier *w, const int16_t *iq, unsigned lane,
                             const unsigned *epochs, int count) {
    enum { padding = 32 };
    if (!w || !iq || lane > 1 || !epochs || count < 1 || count > 2)
        return -1;
    for (int i = 0; i < count; ++i)
        if (epochs[i] < 2 || epochs[i] >= n - 2)
            return portable_verifier_load(w, iq, lane);
    for (int i = 0; i < count; ++i)
        for (int f = 0; f < max_frames; ++f) {
            int origin = frame_start(epochs[i], f);
            int begin = origin + first - padding, end = origin + stop + padding;
            if (begin >= samples) break;
            if (end > samples) end = samples;
            for (int j = begin; j < end; ++j) {
                const int16_t *sample = iq + 4 * j + 2 * lane;
                w->iq.fine[j] = (PortableFineSample){sample[0], sample[1]};
            }
        }
    return 0;
}

/* With a supplied fractional time and carrier, perform the original separate
   exact and rolled checks without deriving a fractional peak from five epochs. */
int directed_verify_fixed(PortableVerifier *w, unsigned epoch, double hz, double offset,
                          int allow_phase_free, PortableVerifierResult *out) {
    if (!w || !out || epoch >= n || !isfinite(hz) || fabs(hz) > rate / 2 ||
        !isfinite(offset) || fabs(offset) > 2.)
        return -1;
    w->phase_margin_radius = 0.;
    *out = (PortableVerifierResult){.acquired_hz = hz, .offset_samples = offset};
    if (glrt(w, epoch, hz, offset, &out->fractional_exact, &out->fractional_control,
             &out->fractional_residual_hz, &out->flags, allow_phase_free))
        return -1;
    if (passes(out->fractional_exact - out->fractional_control, &out->flags))
        out->flags |= PORTABLE_VERIFIER_FRACTIONAL_GATE;
    return 0;
}
