#ifndef LEO_ORDINARY_FRONT_FILTER_H
#define LEO_ORDINARY_FRONT_FILTER_H

#include <complex.h>
#include <math.h>

typedef struct {
    double fraction;
    double weights[16];
    double normalizer;
} leo_fractional_filter;

/* Each output executes the original sixteen tap additions, in order. The
 * four independent accumulators expose parallelism across sample positions. */
static inline void leo_fractional_filter_apply(
    const double complex *samples, int first, int stop, int start, double offset,
    leo_fractional_filter *filter, double complex *output)
{
    for (int k = first; k < stop;) {
        double position = start + k + offset;
        int base = (int)position;
        double fraction = position - base;
        if (fraction != filter->fraction) {
            filter->normalizer = 0;
            for (int tap = -7; tap <= 8; ++tap) {
                double distance = position - (base + tap);
                filter->weights[tap + 7] = sinc(distance) * sinc(distance / 8);
                filter->normalizer += filter->weights[tap + 7];
            }
            filter->fraction = fraction;
        }
        const double complex *input = samples + base - 7;
        int four = k <= stop - 4;
        for (int i = 1; i < 4 && four; ++i) {
            double next = start + (k + i) + offset;
            four = (int)next == base + i && next - (base + i) == fraction;
        }
        if (four) {
            double complex a = 0, b = 0, c = 0, d = 0;
            for (int tap = 0; tap < 16; ++tap) {
                double weight = filter->weights[tap];
                a += weight * input[tap];
                b += weight * input[tap + 1];
                c += weight * input[tap + 2];
                d += weight * input[tap + 3];
            }
            output[k] = a / filter->normalizer;
            output[k + 1] = b / filter->normalizer;
            output[k + 2] = c / filter->normalizer;
            output[k + 3] = d / filter->normalizer;
            k += 4;
        } else {
            double complex a = 0;
            for (int tap = 0; tap < 16; ++tap) a += filter->weights[tap] * input[tap];
            output[k++] = a / filter->normalizer;
        }
    }
}

#endif
