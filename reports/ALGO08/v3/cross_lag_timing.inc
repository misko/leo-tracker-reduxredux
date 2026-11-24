/* Reuse the exact two cue-lag powers if the original timing search is needed. */
enum { cue_epochs = 3333, cue_lag_a = 5, cue_lag_b = 6 };
typedef struct { double contrast; int distance, expanded; } Cue;
static _Thread_local Cue cue;
static _Thread_local int mode, distance_limit;
static _Thread_local double contrast_limit;

void set_cross_lag_rule(int choice, int distance, double contrast) {
    mode = choice;
    distance_limit = distance;
    contrast_limit = contrast;
    cue = (Cue){0., 0, 0};
}

void read_cross_lag_cue(Cue *out) { *out = cue; }

static int cyclic_distance(int a, int b, int period) {
    int distance = abs(a - b);
    return distance < period - distance ? distance : period - distance;
}

static int timing_best(const double *scores, int count) {
    int best = 0;
    for (int i = 1; i < count; ++i)
        if (scores[i] > scores[best]) best = i;
    return best;
}

static double timing_contrast(const double *scores, int index, int radius, int count) {
    double second = 0.;
    for (int i = 0; i < count; ++i) {
        if (cyclic_distance(i, index, count) > radius && scores[i] > second) second = scores[i];
    }
    return second > 0. ? scores[index] / second : NAN;
}

static void timing_peaks(double *scores, int count, int radius, int *epochs, int rows) {
    for (int k = 0; k < rows; ++k) {
        int best = timing_best(scores, count);
        epochs[k] = best;
        for (int j = -radius; j <= radius; ++j) scores[(best + j + count) % count] = -1.;
    }
}

static int cross_lag_times(TimingFirst *w, int *epochs) {
    if (!mode || w->epochs != cue_epochs) {
        find_times(w, epochs);
        return clocks;
    }
    const int packed = __builtin_cpu_supports("avx2");
    const int radius = (int)nearbyint(6. / w->stride);
    double a[cue_epochs] = {0.}, b[cue_epochs] = {0.};
    score_lag(w, a, cue_lag_a, packed);
    score_lag(w, b, cue_lag_b, packed);
    const int best_a = timing_best(a, cue_epochs), best_b = timing_best(b, cue_epochs);
    const double ca = timing_contrast(a, best_a, radius, cue_epochs);
    const double cb = timing_contrast(b, best_b, radius, cue_epochs);
    cue.contrast = isfinite(ca) && isfinite(cb) ? fmin(ca, cb) : NAN;
    cue.distance = cyclic_distance(best_a, best_b, cue_epochs);
    cue.expanded = mode == 2 || (mode == 3 &&
        (!isfinite(cue.contrast) || cue.distance > distance_limit || cue.contrast < contrast_limit));
    if (cue.expanded) {
        memset(w->time_score, 0, cue_epochs * sizeof(*w->time_score));
        for (int k = 0; k < lags; ++k) {
            const double *lag = k == cue_lag_a ? a : k == cue_lag_b ? b : NULL;
            if (lag) {
                for (int i = 0; i < cue_epochs; ++i) w->time_score[i] += lag[i];
            } else {
                score_lag(w, w->time_score, k, packed);
            }
        }
    } else {
        for (int i = 0; i < cue_epochs; ++i) w->time_score[i] = a[i] + b[i];
    }
    const int rows = cue.expanded ? clocks : 4;
    timing_peaks(w->time_score, cue_epochs, radius, epochs, rows);
    return rows;
}
