#include "repeat_negative.c"

static double interval_excess(const int16_t *iq, const int *starts, int lag) {
    double peak = 0.0;
    for (int block = 0; block < 2; ++block) {
        for (int tile = 0; tile < tiles; ++tile) {
            const int sample = starts[block] + tile * frame_ticks / (3 * tiles);
            const int16_t *left = iq + 4 * sample;
            const int16_t *right = left + 4 * lag;
            const double on = coherence(left, right);
            const double early = coherence(left, right - 4 * 61);
            const double late = coherence(left, right + 4 * 61);
            const double excess = on - (early > late ? early : late);
            if (excess > peak)
                peak = excess;
        }
    }
    return peak;
}

double late_pilot_score(const int16_t *iq, int length, int lane, int lag) {
    if (!iq || length != 200000 || lane < 0 || lane > 1 || (lag != 40000 && lag != 38976))
        return NAN;
    const int early[] = {64, 24000};
    const int late[] = {80064, 144000};
    const int16_t *samples = iq + lane * 2;
    return interval_excess(samples, late, lag) - interval_excess(samples, early, lag);
}
