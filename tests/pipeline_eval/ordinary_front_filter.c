#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define TAU 6.283185307179586476925286766559
static double sinc(double x) { return x == 0 ? 1 : sin(TAU*0.5*x)/(TAU*0.5*x); }
#include "ordinary_front_filter.h"

static void scalar(const double complex *samples, int start, int count, double offset,
                   double complex *output)
{
    double previous = NAN, weights[16], normalizer = 0;
    for (int k = 0; k < count; ++k) {
        double position = start + k + offset;
        int base = (int)position;
        double fraction = position - base;
        if (fraction != previous) {
            normalizer = 0;
            for (int tap = -7; tap <= 8; ++tap) {
                double distance = position - (base + tap);
                weights[tap + 7] = sinc(distance) * sinc(distance / 8);
                normalizer += weights[tap + 7];
            }
            previous = fraction;
        }
        double complex received = 0;
        for (int tap = -7; tap <= 8; ++tap) received += weights[tap + 7] * samples[base + tap];
        output[k] = received / normalizer;
    }
}

int main(void)
{
    static double complex samples[200000];
    uint32_t value = 720119;
    for (int k = 0; k < 200000; ++k) {
        value = value * 1664525u + 1013904223u;
        samples[k] = (int16_t)value + I * (int16_t)(value >> 16);
    }
    const int starts[] = {31, 61, 126, 254, 1021, 8190, 16380, 131068, 199930};
    const double offsets[] = {0.3, -0.69, -1.91, 1.781, 0.5000000000001, -0.0};
    for (size_t i = 0; i < sizeof(starts) / sizeof(starts[0]); ++i) {
        for (size_t j = 0; j < sizeof(offsets) / sizeof(offsets[0]); ++j) {
            double complex expected[47], output[47];
            leo_fractional_filter filter = {.fraction = NAN};
            scalar(samples, starts[i], 47, offsets[j], expected);
            // Consecutive calls exercise carry of the cached rounded fraction.
            leo_fractional_filter_apply(samples, 0, 26, starts[i], offsets[j], &filter, output);
            leo_fractional_filter_apply(samples, 26, 47, starts[i], offsets[j], &filter, output);
            if (memcmp(expected, output, sizeof(output))) return 1;
        }
    }
    return 0;
}
