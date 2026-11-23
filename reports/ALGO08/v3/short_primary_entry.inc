/* Adapt the existing primary-only branch to the released v3 verify_peaks helper.
   This translation unit is linked only against the authenticated 12 ms objects. */
int cancellation_primary_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                 double lo, double hi, ScanFactor out[2]) {
    if (!r || !out) return -1;
    TimingFirstResult scouts[2] = {{0}, {0}};
    if (timing_first_detect(r->timing, iq, lane, lo, hi, &scouts[0])) return -1;
    if (!scouts[0].confirmation) return 0;
    if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;
    TwoCarrierPeak peaks[2];
    return verify_peaks(r, scouts, peaks, out, 1);
}
