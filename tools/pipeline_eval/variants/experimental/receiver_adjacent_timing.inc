int timing_adjacent_configure(TimingFirst *w, const DifferentialFilter *filters, const double *energy) {
    if (!w || !filters || !energy) return -1;
    if (!w->adjacent) w->adjacent = leo_differential_scout_create();
    if (!w->adjacent) return -1;
    w->adjacent_filters = filters;
    w->adjacent_energy = energy;
    return 0;
}

void timing_adjacent_mode(TimingFirst *w, AdjacentStats *stats, int fallback) {
    w->adjacent_stats = stats;
    w->adjacent_fallback = fallback;
}

static int adjacent_epochs(TimingFirst *w, const int16_t *iq, int lane, int *down, int *native) {
    enum { separation = 5 };
    double score[period];
    leo_differential_scout_lane(w->adjacent, iq, lane, w->adjacent_filters, w->adjacent_energy, score);
    const double first = score[0];
    double previous = score[period - 1];
    for (int e = 0; e < period; ++e) {
        const double value = score[e], next = e == period - 1 ? first : score[e + 1];
        if (!(value > 0. && value >= previous && value >= next && (value > previous || value > next)))
            score[e] = 0.;
        previous = value;
    }
    int used = 0;
    for (; used < clocks; ++used) {
        int best = -1;
        double power = 0.;
        for (int e = 0; e < period; ++e) {
            if (score[e] > power) {
                best = e;
                power = score[e];
            }
        }
        if (best < 0) break;
        for (int d = 1 - separation; d < separation; ++d)
            score[(best + period + d) % period] = 0.;
        native[used] = best;
        down[used] = (int)nearbyint((double)best / w->stride);
    }
    return used;
}
