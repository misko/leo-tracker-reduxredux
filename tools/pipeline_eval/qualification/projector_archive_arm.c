/* Read one little-endian orbital projection fixture and emit raw double arrays. */
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(double) == sizeof(int64_t) && DBL_MANT_DIG == 53,
               "the fixture requires binary64 doubles");
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__,
               "the fixture uses little-endian binary data");

int project_orbit_grid(const double *, const double *, size_t, size_t, size_t, size_t,
                       const int64_t *, const double *, const double *, double,
                       const double *, const double *, double, double *, double *, double *);

static int product(size_t a, size_t b, size_t *result)
{
    if (b && a > SIZE_MAX / b) return 0;
    *result = a * b;
    return 1;
}

int main(void)
{
    unsigned char magic[8];
    uint64_t shape[4];
    double settings[8];
    if (fread(magic, sizeof magic, 1, stdin) != 1 || memcmp(magic, "LEOPROJ1", 8) ||
        fread(shape, sizeof shape, 1, stdin) != 1 ||
        fread(settings, sizeof settings, 1, stdin) != 1) return 2;
    for (size_t i = 0; i < 4; ++i) {
        if (!shape[i] || shape[i] > SIZE_MAX) return 2;
    }
    for (size_t i = 0; i < 8; ++i) {
        if (!isfinite(settings[i])) return 2;
    }
    if (!(settings[0] > 0) || !(settings[1] > 0)) return 2;
    size_t satellites = shape[0], knots = shape[1], times = shape[2], groups = shape[3];
    size_t coordinates, stencil, rotation, cells;
    if (knots < 2 || (groups != 1 && groups != satellites) ||
        !product(satellites, knots, &coordinates) || !product(coordinates, 3, &coordinates) ||
        !product(groups, times, &stencil) || !product(stencil, 3, &stencil) ||
        !product(groups, 6, &rotation) || !product(satellites, times, &cells)) return 2;

    size_t input_bytes = 0, output_bytes;
    const size_t input_words[] = {coordinates, coordinates, stencil, stencil, rotation};
    for (size_t i = 0; i < sizeof input_words / sizeof input_words[0]; ++i) {
        size_t bytes;
        if (!product(input_words[i], sizeof(double), &bytes) || bytes > SIZE_MAX - input_bytes)
            return 2;
        input_bytes += bytes;
    }
    if (!product(cells, 3 * sizeof(double), &output_bytes) ||
        output_bytes > SIZE_MAX - input_bytes) return 2;

    double *block = malloc(input_bytes + output_bytes);
    if (!block) return 3;
    int status = 2;
    if (fread(block, 1, input_bytes, stdin) == input_bytes && fgetc(stdin) == EOF && !ferror(stdin)) {
        double *vel = block + coordinates;
        int64_t *idx = (int64_t *)(vel + coordinates);
        double *frac = (double *)(idx + stencil);
        double *rot = frac + stencil;
        double *frequency = rot + rotation;
        int result = project_orbit_grid(block, vel, satellites, knots, times, groups, idx,
                                        frac, rot, settings[0], settings + 2, settings + 5,
                                        settings[1], frequency, frequency + cells,
                                        frequency + 2 * cells);
        if (!result && fwrite(frequency, 1, output_bytes, stdout) == output_bytes && !fflush(stdout)) {
            fprintf(stderr, "{\"input_array_bytes\":%zu,\"output_array_bytes\":%zu,"
                            "\"array_allocations\":1}\n", input_bytes, output_bytes);
            status = 0;
        } else {
            status = result ? 3 + result : 6;
        }
    }
    free(block);
    return status;
}
