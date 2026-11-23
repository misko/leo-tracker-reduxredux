#include <math.h>
#include <stdint.h>

enum { frame_ticks = 40000, tiles = 12, pairs = 64, sample_stride = 4 };

static double coherence(const int16_t *left, const int16_t *right) {
    int64_t lr = 0, li = 0, rr = 0, ri = 0, le = 0, re = 0, dot_r = 0, dot_i = 0;
    for (int i = 0; i < pairs; ++i) {
        const int n = i * sample_stride * 4;
        const int64_t ar = left[n], ai = left[n + 1], br = right[n], bi = right[n + 1];
        lr += ar;
        li += ai;
        rr += br;
        ri += bi;
        le += ar * ar + ai * ai;
        re += br * br + bi * bi;
        dot_r += ar * br + ai * bi;
        dot_i += ar * bi - ai * br;
    }
    const int64_t left_power = pairs * le - lr * lr - li * li;
    const int64_t right_power = pairs * re - rr * rr - ri * ri;
    if (left_power == 0 || right_power == 0)
        return 0.0;
    const double real = (double)(pairs * dot_r - lr * rr - li * ri);
    const double imag = (double)(pairs * dot_i - lr * ri + li * rr);
    return (real * real + imag * imag) / ((double)left_power * (double)right_power);
}

double repeat_negative_score(const int16_t *iq, int length, int lane, int aperture) {
    if (!iq || length != 200000 || lane < 0 || lane > 1 || (aperture != 12 && aperture != 20))
        return NAN;
    const int blocks[] = {64, 64 + (aperture == 12 ? 4 : 10) * frame_ticks / 3};
    double peak = 0.0;
    for (int block = 0; block < 2; ++block) {
        for (int tile = 0; tile < tiles; ++tile) {
            const int sample = blocks[block] + tile * frame_ticks / (3 * tiles);
            const int16_t *left = iq + sample * 4 + lane * 2;
            const int16_t *right = left + 4 * frame_ticks;
            const double lagged = coherence(left, right);
            const double early = coherence(left, right - 4 * 61);
            const double late = coherence(left, right + 4 * 61);
            const double excess = lagged - (early > late ? early : late);
            if (excess > peak)
                peak = excess;
        }
    }
    return peak;
}
