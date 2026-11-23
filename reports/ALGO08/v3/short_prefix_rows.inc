/* Inspect the pinned original verifier workspace immediately after a call. */
int short_prefix_rows(const PortableVerifier *w, int frames, double state[2], GlrtComplex *out)
{
    if (!w || !state || !out || frames < 1 || frames > max_frames)
        return -1;
    state[0] = w->integer_hz;
    state[1] = w->phase_margin_radius;
    for (int pilot = 0; pilot < 2; ++pilot)
        memcpy(out + pilot * frames * 64, w->correlations[pilot],
               (size_t)frames * 64 * sizeof(*out));
    return 0;
}
