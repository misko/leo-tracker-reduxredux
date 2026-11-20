#ifndef LEO_FRACTIONAL_RUNTIME_H
#define LEO_FRACTIONAL_RUNTIME_H

#if defined(__SSE2__)
#include <emmintrin.h>
typedef __m128d leo_fractional_weight;
#else
typedef double leo_fractional_weight;
#endif

typedef struct {
    double fraction;
    leo_fractional_weight taps[16];
    double normalizer;
} leo_fractional_runtime;

/* Include the full allowed offset range and a sample of rounding slack.
 * Within this binade each integer is an even multiple of the FP64 ulp.
 * Translating by one integer leaves the rounded fraction and ties invariant. */
static inline int leo_fractional_one_binade(int first, int stop)
{
    if (first < 4 || stop <= first) return 0;
    unsigned low = (unsigned)first - 3;
    unsigned high = (unsigned)stop + 2;
    return __builtin_clz(low) == __builtin_clz(high);
}

static inline int leo_fractional_runtime_base(leo_fractional_runtime *filter,
    int coordinate, double offset)
{
    double position = coordinate + offset;
    int base = (int)position;
    double fraction = position - base;
    if (filter->fraction != fraction) {
        filter->normalizer = 0;
        for (int tap = -7; tap <= 8; ++tap) {
            double distance = position - (base + tap);
            double weight = sinc(distance) * sinc(distance / 8);
#if defined(__SSE2__)
            filter->taps[tap + 7] = _mm_set1_pd(weight);
#else
            filter->taps[tap + 7] = weight;
#endif
            filter->normalizer += weight;
        }
        filter->fraction = fraction;
    }
    return base;
}

static inline double complex leo_fractional_runtime_dot(
    const leo_fractional_runtime *filter, const double complex *input)
{
#if defined(__SSE2__)
    __m128d accum = _mm_setzero_pd();
    for (int tap = 0; tap < 16; ++tap) {
        __m128d sample;
        memcpy(&sample, input + tap, sizeof(sample));
        accum = _mm_add_pd(accum, _mm_mul_pd(sample, filter->taps[tap]));
    }
    accum = _mm_div_pd(accum, _mm_set1_pd(filter->normalizer));
    double complex result;
    memcpy(&result, &accum, sizeof(result));
    return result;
#else
    double complex accum = 0;
    for (int tap = 0; tap < 16; ++tap) accum += filter->taps[tap] * input[tap];
    return accum / filter->normalizer;
#endif
}

#endif
