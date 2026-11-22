typedef struct {
    const TimingHint *hints;
    unsigned count;
    int full;
    TrackingStats *stats;
} TrackingPlan;

static int search_visit(TimingFirst *timing, const int16_t *iq, int lane, double lo, double hi,
                        TimingFirstResult *out, const TrackingPlan *plan, const TimingFirstResult *prior) {
    if (!plan || plan->full) {
        if (plan && prior) ++plan->stats->global_residual;
        if (plan && !prior) ++plan->stats->global_first;
        return timing_first_detect(timing, iq, lane, lo, hi, out);
    }
    TimingHint hints[max_tracking_hints];
    unsigned count = 0;
    for (unsigned i = 0; i < plan->count; ++i) {
        TimingHint hint = plan->hints[i];
        if (!prior || !same_peak(hint.epoch, hint.hz, prior->epoch, prior->hz)) hints[count++] = hint;
    }
    if (!prior && count) {
        ++plan->stats->narrow_first;
        if (experimental_timing_detect(timing, iq, lane, lo, hi, out, hints, count, 2)) return -1;
        if (out->confirmation) return 0;
    }
    if (prior) ++plan->stats->short_residual;
    else ++plan->stats->short_first;
    return experimental_timing_detect(timing, iq, lane, lo, hi, out, hints, prior ? count : 0, 1);
}
