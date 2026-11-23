/* Both callbacks use the same authorized 20 ms verifier and reducer. */
int short_cfo_independent(PortableVerifier *w, const PortableVerifier *prefix,
                          const int16_t *iq, unsigned lane, unsigned epoch,
                          double offset, double seed, double cfo, double out[8], int *used)
{
    (void)prefix;
    (void)seed;
    *used = 0;
    return short_cfo_refine(w, iq, lane, epoch, offset, cfo, out);
}

int short_cfo_reuse(PortableVerifier *w, const PortableVerifier *prefix,
                    const int16_t *iq, unsigned lane, unsigned epoch,
                    double offset, double seed, double cfo, double out[8], int *used)
{
    enum { reused_frames = 8 };
    *used = 0;
    if (!w || !prefix || w == prefix || !iq || lane > 1 || epoch >= n ||
        !isfinite(cfo) || fabs(cfo) > 5e6 || !isfinite(offset) || fabs(offset) > 1.5 ||
        memcmp(&seed, &cfo, sizeof(cfo)) || prefix->phase_margin_radius != 0.)
        return short_cfo_independent(w, prefix, iq, lane, epoch, offset, seed, cfo, out, used);

    const int integer = fabs(offset - nearbyint(offset)) <= 1e-12;
    int32_t starts[max_frames];
    int group[max_frames], frames = 0;
    for (int frame = 0; frame < max_frames; ++frame) {
        const int start = frame_start(epoch, frame);
        const double first_position = start + first + offset;
        const double last_position = start + stop - 1 + offset;
        const int lo = (int)floor(first_position) - (integer ? 0 : 7);
        const int hi = (int)floor(last_position) + (integer ? 0 : 8);
        if (lo < 0 || hi >= samples) break;
        if (frame < reused_frames &&
            (first_position < (integer ? 0 : 7) || last_position >= short_limit - (integer ? 0 : 8)))
            return short_cfo_independent(w, prefix, iq, lane, epoch, offset, seed, cfo, out, used);
        starts[frames] = start;
        group[frames++] = hi < short_limit ? 0 : lo >= short_limit ? 1 : -1;
    }
    if (frames <= reused_frames ||
        load_frame_support(w, iq, lane, starts + reused_frames, frames - reused_frames, offset, integer))
        return short_cfo_independent(w, prefix, iq, lane, epoch, offset, seed, cfo, out, used);

    if (integer) {
        for (int f = reused_frames; f < frames; ++f)
            starts[f] += first + (int)nearbyint(offset);
        prepare_integer_rotation(w, cfo);
        const int32_t zero = 0;
        correlated_integer(w->iq.glrt, starts + reused_frames, 1, frames - reused_frames, &zero,
                           w->glrt_rotation, w->glrt_exact, w->glrt_control,
                           w->correlations[0] + reused_frames * 64, w->correlations[1] + reused_frames * 64);
    } else if (absolute_fractional_tail(w, frames - reused_frames, starts + reused_frames, cfo, offset)) {
        return short_cfo_independent(w, prefix, iq, lane, epoch, offset, seed, cfo, out, used);
    }
    for (int pilot = 0; pilot < 2; ++pilot)
        memcpy(w->correlations[pilot], prefix->correlations[pilot],
               reused_frames * 64 * sizeof(*w->correlations[pilot]));

    *used = reused_frames;
    return score_parts(w->correlations[0], w->correlations[1], frames, group, out);
}
