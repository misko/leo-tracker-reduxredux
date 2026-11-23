/* Appended to the pinned 12 ms receiver translation unit. The caller retains
 * the original stereo CI16 storage and the original 20 ms capture metadata. */
int cancellation_primary_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                 double lo, double hi, ScanFactor out[2]) {
    enum { center_start = 40000, aperture = 120000, shorts_per_sample = 4 };
    _Static_assert(center_start + aperture <= samples, "Centered aperture exceeds the visit");
    /* The scout and verifier repeat their fractional frame grid every 40000
     * samples. Local frame f is original frame f+3 with the same pilot epoch. */
    if (!iq) return -1;
    return primary_on_aperture(r, iq + center_start * shorts_per_sample, lane, lo, hi, out);
}
