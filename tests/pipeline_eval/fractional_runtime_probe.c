#include <complex.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static double sinc(double x)
{
    const double pi = 3.141592653589793238462643383279502884;
    return x == 0 ? 1 : sin(pi * x) / (pi * x);
}

#include "fractional_runtime.h"

static int verify(int first, int stop, double offset)
{
    double complex data[96];
    for (int k = 0; k < 96; ++k)
        data[k] = ((18201 * k + 173) % 65536 - 32768) + I * ((9127 * k + 511) % 65536 - 32768);
    leo_fractional_runtime filter = {.fraction = NAN};
    int reusable = leo_fractional_one_binade(first, stop);
    int base = leo_fractional_runtime_base(&filter, first, offset);
    for (int k = first; k < stop; ++k) {
        if (!reusable && k != first) base = leo_fractional_runtime_base(&filter, k, offset);
        double position = k + offset;
        int expected_base = (int)position;
        double norm = 0;
        double complex expected = 0;
        for (int tap = -7; tap <= 8; ++tap) {
            double distance = position - (expected_base + tap);
            double weight = sinc(distance) * sinc(distance / 8);
            norm += weight;
            expected += weight * data[k - first + tap + 7];
        }
        expected /= norm;
        double complex result = leo_fractional_runtime_dot(&filter, data + k - first);
        if (base != expected_base || memcmp(&result, &expected, sizeof(result))) {
            fprintf(stderr, "position %d offset %a reusable %d\n", k, offset, reusable);
            return 1;
        }
        ++base;
    }
    return 0;
}

int main(void)
{
    double offsets[] = {-.731428324780195, .731428324780195, -1.917,
        nextafter(0, 1), nextafter(1, 0), nextafter(-1, -2), 0x1p-35, -0x1p-35};
    for (int e = 6; e <= 28; ++e) {
        int boundary = 1 << e;
        for (size_t u = 0; u < sizeof(offsets) / sizeof(*offsets); ++u) {
            if (verify(boundary - 56, boundary + 3, offsets[u]) ||
                verify(boundary + 8, boundary + 62, offsets[u])) return 1;
        }
    }
    return 0;
}
