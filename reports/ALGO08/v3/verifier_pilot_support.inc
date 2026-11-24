/* Populate only the original samples reached by the unchanged five-position
   integer stencil and its fractional refinement, for at most two scouts. */
static _Thread_local uint64_t support_counts[3];

void portable_verifier_support_counts(uint64_t out[3], int reset)
{
    memcpy(out, support_counts, sizeof(support_counts));
    if (reset) memset(support_counts, 0, sizeof(support_counts));
}

static void support_copy(PortableVerifier *w, const int16_t *iq, unsigned lane, int lo, int hi)
{
    for (int sample = lo; sample < hi; ++sample) {
        size_t index = 4 * (size_t)sample + 2 * lane;
        w->iq.fine[sample] = (PortableFineSample){iq[index], iq[index + 1]};
    }
    support_counts[1] += (unsigned)(hi - lo);
}

int portable_verifier_load_support(PortableVerifier *w, const int16_t *iq, unsigned lane,
                                  unsigned a, unsigned b)
{
    if (!w || !iq || lane > 1) return -1;
    ++support_counts[0];
    /* A wrapped stencil can use a different origin at either end. Keep the
       original loader for those calls. n denotes an absent second scout. */
    if (a < 2 || a >= n - 2 || (b != n && (b < 2 || b >= n - 2))) {
        ++support_counts[2];
        support_counts[1] += SUPPORT_LOADED_SAMPLES;
        return portable_verifier_load(w, iq, lane);
    }
    unsigned early = a < b ? a : b, late = a < b ? b : a;
    int lo = 0, hi = 0;
    for (unsigned frame = 0; frame < SUPPORT_ANALYSIS_FRAMES; ++frame) {
        for (int scout = 0; scout < 1 + (late != n && late != early); ++scout) {
            int origin = frame_start(scout ? late : early, frame);
            /* floor(epoch_offset) is in [-2, 1]. The sixteen-tap
               interpolation then needs seven before and eight after. */
            int start = origin + first - 9;
            int end = origin + stop + 9;
            if (start >= SUPPORT_LOADED_SAMPLES) break;
            if (end > SUPPORT_LOADED_SAMPLES) end = SUPPORT_LOADED_SAMPLES;
            if (start > hi) {
                if (hi > lo) support_copy(w, iq, lane, lo, hi);
                lo = start;
            }
            if (end > hi) hi = end;
        }
    }
    if (hi > lo) support_copy(w, iq, lane, lo, hi);
    return 0;
}
