/* Timing on a warm lane can start directly from its own measurements. The
   retained pilot gate still tests the current samples on independent frames. */
static int refine_hint(TimingFirst *w, TimingHint hint, double lo, double hi, Peak *peak) {
    if (hint.epoch < 0 || hint.epoch >= period || !(hint.hz >= lo && hint.hz <= hi)) return 0;
    double v[4];
    if (delay_refine((float *)w->data, (float *)(w->pilot + first), hint.epoch, hint.hz, lo, hi, v))
        return -1;
    if (fabs(remainder(v[2] - hint.epoch, period)) >= 4. || fabs(v[1] - hint.hz) > 1250.) return 0;
    *peak = (Peak){v[0], v[1], v[3], (int)v[2]};
    return 1;
}

static int find_confirmed(TimingFirst *w, Peak *peaks, int done, TimingFirstResult *out) {
    for (int k = 0; k < done; ++k) {
        int best = 0;
        for (int i = 1; i < done; ++i)
            if (peaks[i].score > peaks[best].score) best = i;
        Peak p = peaks[best];
        peaks[best].score = -1.;
        int why = 0;
        if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0)) why = 1;
        else if (gate(w, &p, 0, 1)) why = 2;
        if (why) {
            *out = (TimingFirstResult){p.epoch, p.hz, p.score, why};
            return 1;
        }
    }
    return 0;
}
