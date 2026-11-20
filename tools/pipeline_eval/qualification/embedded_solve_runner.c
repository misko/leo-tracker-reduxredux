/* Replay precomputed fixed-owner linearizations on Linux host or AArch64. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int leo_embedded_bvls(size_t, size_t, const double *, const double *, const double *,
                      const double *, double *, double *, double *, size_t *);

static double now(void)
{
    struct timespec stamp;
    clock_gettime(CLOCK_MONOTONIC, &stamp);
    return (double)stamp.tv_sec + (double)stamp.tv_nsec * 1e-9;
}

static void geodetic(const double *region, const double *state, double *lat, double *lon)
{
    const double a = 6378.137, f = 1.0 / 298.257223563;
    const double b = a * (1.0 - f), e2 = f * (2.0 - f), deg = 180.0 / acos(-1.0);
    double p[3];
    for (size_t i = 0; i < 3; ++i)
        p[i] = region[i] + state[0] * region[3 + i] + state[1] * region[6 + i];
    double radial = hypot(p[0], p[1]);
    double theta = atan2(a * p[2], b * radial);
    double s = sin(theta), c = cos(theta);
    *lat = deg * atan2(p[2] + e2 / (1.0 - e2) * b * s * s * s,
                       radial - e2 * a * c * c * c);
    *lon = deg * atan2(p[1], p[0]);
}

int main(int argc, char **argv)
{
    unsigned long repeat = argc == 2 ? strtoul(argv[1], NULL, 10) : 0;
    if (!repeat || repeat > 1000000)
        return 1;
    uint32_t shape[3];
    double region[9];
    if (fread(shape, sizeof(*shape), 3, stdin) != 3 || fread(region, sizeof(*region), 9, stdin) != 9)
        return 1;
    size_t width = shape[0], orbits = shape[1], count = shape[2];
    if ((width != 10 && width != 11) || orbits > 4096 || count == 0 || count > 4)
        return 1;
    size_t n = width + orbits, elements = width * (width + 1) + orbits * (width + 2) + n;
    double *data = malloc((elements + 2 * n) * sizeof(*data));
    if (!data)
        return 1;
    double *trial = data + elements, *state = trial + n;
    double covariance[4], kkt, worst = 0.0, seconds = 0.0;
    memset(state, 0, n * sizeof(*state));
    size_t steps, bound_updates = 0;
    for (size_t i = 0; i < count; ++i) {
        double alpha;
        if (fread(&alpha, sizeof(alpha), 1, stdin) != 1 || !(alpha >= 0.0 && alpha <= 1.0)
            || fread(data, sizeof(*data), elements, stdin) != elements) {
            free(data);
            return 1;
        }
        const double *rhs = data + width * width, *orbit = rhs + width;
        const double *bound = orbit + orbits * (width + 2);
        double started = now();
        for (unsigned long j = 0; j < repeat; ++j) {
            if (leo_embedded_bvls(width, orbits, data, rhs, orbit, bound, trial, covariance,
                                  &kkt, &steps)) {
                free(data);
                return 2;
            }
        }
        seconds += now() - started;
        for (size_t j = 0; j < n; ++j)
            state[j] += alpha * (trial[j] - state[j]);
        worst = fmax(worst, kkt);
        bound_updates += steps;
    }
    if (fgetc(stdin) != EOF) {
        free(data);
        return 1;
    }
    double lat, lon;
    geodetic(region, state, &lat, &lon);
    printf("{\"latlon\":[%.17g,%.17g],\"coefficients\":[", lat, lon);
    for (size_t i = 0; i < n; ++i)
        printf("%s%.17g", i ? "," : "", state[i]);
    printf("],\"worst_scaled_kkt\":%.17g,\"bound_updates\":%zu,"
           "\"mean_solve_wall_s\":%.17g,\"linearizations\":%zu,"
           "\"array_and_kernel_heap_bytes\":%zu}\n",
           worst, bound_updates, seconds / ((double)repeat * (double)count), count,
           (elements + 3 * n) * sizeof(*data) + n * sizeof(int8_t));
    free(data);
    return 0;
}
