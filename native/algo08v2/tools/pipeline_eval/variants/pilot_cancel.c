/* One step of successive pilot cancellation, with a separate complex gain per block. */
#include "pilot_cancel.h"

#include <math.h>
#include <string.h>

enum { samples = 200000, thirds = 40000, symbol = 132, first_symbol = 2, end_symbol = 302 };

static int first_sample(int tick) {
    int n = tick / 3 + (tick % 3 > 0);
    return n < 0 ? 0 : n > samples ? samples : n;
}

static int16_t quantize(double value) {
    return (int16_t)lrint(fmin(32767., fmax(-32768., value)));
}

int pilot_cancel(const int16_t *input, int16_t *output, int lane, const float *pilot,
                 float *scratch, double epoch, double carrier_hz) {
    if (!input || !output || input == output || !pilot || !scratch || lane < 0 || lane > 1 ||
        !isfinite(epoch) || epoch < 0. || epoch >= 13333. || !isfinite(carrier_hz) ||
        fabs(carrier_hz) > 5e6)
        return -1;
    memcpy(output, input, 4 * samples * sizeof(*input));
    const double d = 6.28318530717958647693 * carrier_hz / 3e7;
    const double dr = cos(d), di = sin(d);
    double ar = 1., ai = 0.;
    for (int j = 0; j < thirds; ++j) {
        double pr = pilot[2 * j], pi = pilot[2 * j + 1];
        scratch[2 * j] = (float)(pr * ar - pi * ai);
        scratch[2 * j + 1] = (float)(pi * ar + pr * ai);
        double next = ar * dr - ai * di;
        ai = ar * di + ai * dr;
        ar = next;
    }
    /* At 750 Hz a 10 MS/s frame is exactly 40,000/3 samples. Partial first
       and last blocks use the same recorded samples in the fit and subtraction. */
    for (int t = (int)lrint(3. * epoch) - thirds; t < 3 * samples; t += thirds) {
        for (int block = first_symbol; block < end_symbol; block += 64) {
            const int start = first_sample(t + symbol * block);
            const int end = first_sample(t + symbol * (block + 64 < end_symbol ? block + 64 : end_symbol));
            if (end <= start) continue;
            double norm = 0., re = 0., im = 0.;
            for (int n = start; n < end; ++n) {
                const int j = 2 * (3 * n - t), a = 4 * n + 2 * lane;
                double hr = scratch[j], hi = scratch[j + 1];
                norm += hr * hr + hi * hi;
                re += hr * input[a] + hi * input[a + 1];
                im += hr * input[a + 1] - hi * input[a];
            }
            if (norm == 0.) continue;
            re /= norm;
            im /= norm;
            for (int n = start; n < end; ++n) {
                const int j = 2 * (3 * n - t), a = 4 * n + 2 * lane;
                double hr = scratch[j], hi = scratch[j + 1];
                output[a] = quantize(input[a] - (re * hr - im * hi));
                output[a + 1] = quantize(input[a + 1] - (im * hr + re * hi));
            }
        }
    }
    return 0;
}
