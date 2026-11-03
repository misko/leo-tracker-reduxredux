#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "source/native/adaptive/detector/kernel/private/next_up_positive.h"

static uint64_t bits(double value)
{
    uint64_t result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static double from_bits(uint64_t value)
{
    double result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

__attribute__((noinline)) static double libc_next_up(double value)
{
    volatile double input = value;
    return nextafter(input, INFINITY);
}

static void check_one(double value, int rounding, int initial_flags)
{
    if (fesetround(rounding)) abort();
    feclearexcept(FE_ALL_EXCEPT);
    if (initial_flags) feraiseexcept(initial_flags);
    double expected = libc_next_up(value);
    int expected_flags = fetestexcept(FE_ALL_EXCEPT);

    feclearexcept(FE_ALL_EXCEPT);
    if (initial_flags) feraiseexcept(initial_flags);
    double actual = leo_research_next_up_positive(value);
    int actual_flags = fetestexcept(FE_ALL_EXCEPT);
    if (bits(actual) != bits(expected) || actual_flags != expected_flags) {
        fprintf(stderr,
            "mismatch input=%016llx rounding=%d initial=%x expected=%016llx/%x actual=%016llx/%x\n",
            (unsigned long long)bits(value), rounding, initial_flags,
            (unsigned long long)bits(expected), expected_flags,
            (unsigned long long)bits(actual), actual_flags);
        abort();
    }
}

static uint64_t random64(uint64_t *state)
{
    uint64_t x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    return x * UINT64_C(2685821657736338717);
}

int main(void)
{
    if (sizeof(double) != sizeof(uint64_t) || FLT_RADIX != 2 ||
        DBL_MANT_DIG != 53 || DBL_MAX_EXP != 1024) {
        puts("next-up: unsupported representation used libc fallback");
        return 0;
    }
    const uint64_t cases[] = {
        UINT64_C(0x0000000000000000), UINT64_C(0x8000000000000000),
        UINT64_C(0x0000000000000001), UINT64_C(0x000fffffffffffff),
        UINT64_C(0x0010000000000000), UINT64_C(0x0010000000000001),
        UINT64_C(0x3fefffffffffffff), UINT64_C(0x3ff0000000000000),
        UINT64_C(0x3ff0000000000001), UINT64_C(0x4000000000000000),
        UINT64_C(0x7fdfffffffffffff), UINT64_C(0x7feffffffffffffe),
        UINT64_C(0x7fefffffffffffff), UINT64_C(0x7ff0000000000000),
        UINT64_C(0xfff0000000000000), UINT64_C(0x8000000000000001),
        UINT64_C(0xbff0000000000000), UINT64_C(0x7ff0000000000001),
        UINT64_C(0xfff0000000000001), UINT64_C(0x7ff8000000001234),
    };
    const int roundings[] = {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
    const int initial_flags[] = {0, FE_DIVBYZERO};
    size_t checks = 0;
    for (size_t r = 0; r < sizeof(roundings) / sizeof(roundings[0]); ++r)
        for (size_t f = 0; f < sizeof(initial_flags) / sizeof(initial_flags[0]); ++f)
            for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
                check_one(from_bits(cases[i]), roundings[r], initial_flags[f]);
                ++checks;
            }

    uint64_t state = UINT64_C(0x243f6a8885a308d3);
    for (size_t i = 0; i < 250000; ++i) {
        uint64_t value = random64(&state) & UINT64_C(0x7fffffffffffffff);
        /* Include every class; NaNs and boundaries exercise libc fallback. */
        check_one(from_bits(value), roundings[i & 3], initial_flags[(i >> 2) & 1]);
        ++checks;
    }
    if (fesetround(FE_TONEAREST)) abort();
    printf("next-up: %zu result-bit and exception-flag checks pass\n", checks);
    return 0;
}
