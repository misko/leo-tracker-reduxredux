#include <math.h>
#include <stdint.h>

enum { PREFIX = 40000, TILES = 12, POINTS = 64, STRIDE = 4, DISPLACE = 61 };

struct covariance {
    double re;
    double im;
};

static double closure(const int16_t *samples, int lane, int phase, int shift) {
    const int start[] = {phase, phase + 13333 + shift, phase + 26667 - shift};
    const int left[] = {0, 1, 0};
    const int right[] = {1, 2, 2};
    int64_t re[3] = {0}, im[3] = {0}, energy[3] = {0};
    int64_t cross_re[3] = {0}, cross_im[3] = {0};

    for (int k = 0; k < POINTS; k++) {
        int64_t x[3], y[3];
        for (int i = 0; i < 3; i++) {
            const int16_t *sample = samples + 4 * (start[i] + k * STRIDE) + 2 * lane;
            x[i] = sample[0];
            y[i] = sample[1];
            re[i] += x[i];
            im[i] += y[i];
            energy[i] += x[i] * x[i] + y[i] * y[i];
        }
        for (int i = 0; i < 3; i++) {
            const int a = left[i], b = right[i];
            cross_re[i] += x[a] * x[b] + y[a] * y[b];
            cross_im[i] += x[a] * y[b] - y[a] * x[b];
        }
    }

    for (int i = 0; i < 3; i++) {
        energy[i] = POINTS * energy[i] - re[i] * re[i] - im[i] * im[i];
        if (energy[i] <= 0)
            return NAN;
    }
    struct covariance q[3];
    double powers[3], weakest = 1.0;
    for (int i = 0; i < 3; i++) {
        const int a = left[i], b = right[i];
        q[i].re = POINTS * cross_re[i] - re[a] * re[b] - im[a] * im[b];
        q[i].im = POINTS * cross_im[i] - re[a] * im[b] + im[a] * re[b];
        powers[i] = q[i].re * q[i].re + q[i].im * q[i].im;
        if (powers[i] == 0.0)
            return 0.0;
        weakest = fmin(weakest, powers[i] / ((double)energy[a] * energy[b]));
    }
    const double product_re = q[0].re * q[1].re - q[0].im * q[1].im;
    const double product_im = q[0].re * q[1].im + q[0].im * q[1].re;
    const double aligned = (product_re * q[2].re + product_im * q[2].im) /
        sqrt(powers[0] * powers[1] * powers[2]);
    return weakest * fmax(0.0, fmin(1.0, aligned));
}

double three_origin_score(const int16_t *samples, int count, int lane) {
    if (samples == 0 || count < PREFIX || (lane != 0 && lane != 1))
        return NAN;

    double strongest = 0.0;
    for (int tile = 0; tile < TILES; tile++) {
        const int phase = 64 + tile * PREFIX / (3 * TILES);
        const double nominal = closure(samples, lane, phase, 0);
        const double forward = closure(samples, lane, phase, DISPLACE);
        const double reverse = closure(samples, lane, phase, -DISPLACE);
        if (!isfinite(nominal) || !isfinite(forward) || !isfinite(reverse))
            return NAN;
        strongest = fmax(strongest, nominal - fmax(forward, reverse));
    }
    return strongest;
}
