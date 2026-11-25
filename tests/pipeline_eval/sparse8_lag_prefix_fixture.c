#include <fftw3.h>
#include <math.h>
#include <string.h>

typedef struct { float re, im; } Sample;
static Sample multiply(Sample a, Sample b) {
    return (Sample){a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re};
}
static Sample conjugate(Sample a) { return (Sample){a.re, -a.im}; }
static float power(Sample a) { return a.re * a.re + a.im * a.im; }
#include SPECTRAL_IMPL

int has_avx2(void) { return __builtin_cpu_supports("avx2") != 0; }

void lag_products(Sample *out, double *prefix, const Sample *a, const Sample *b,
                  int width, int lag, int fft_size) {
    spectral_lag_products(out, prefix, a, b, width, lag, fft_size);
}

/* Active stride-4 geometry and original timing loop, downstream of fixed modes. */
int lag_timing(const Sample *a, const Sample *b, const Sample *filters,
               double *scores, double *excluded, int *epochs) {
    enum { size = 4800, width = 4740, grid = 3333, length = 1408, clocks = 12, radius = 2 };
    const int lags[] = {2, 4, 6, 11, 18, 28, 44, 74};
    double prefix[width + 1];
    fftwf_complex *scratch = fftwf_alloc_complex(size);
    if (!scratch) return -1;
    fftwf_plan forward = fftwf_plan_dft_1d(size, scratch, scratch, FFTW_FORWARD, FFTW_ESTIMATE);
    fftwf_plan backward = fftwf_plan_dft_1d(size, scratch, scratch, FFTW_BACKWARD, FFTW_ESTIMATE);
    int ready = forward && backward;
    Sample *out = (Sample *)scratch;
    if (ready) {
        memset(scores, 0, grid * sizeof(*scores));
        for (int k = 0; k < 8; ++k) {
            int lag = lags[k];
            spectral_lag_products(out, prefix, a, b, width, lag, size);
            fftwf_execute(forward);
            spectral_filter(out, filters + k * size, size);
            fftwf_execute(backward);
            spectral_timing_scores(scores, prefix, out, grid, length - lag, size);
        }
        memcpy(excluded, scores, grid * sizeof(*scores));
        for (int k = 0; k < clocks; ++k) {
            int best = 0;
            for (int i = 1; i < grid; ++i)
                if (excluded[i] > excluded[best]) best = i;
            epochs[k] = best;
            for (int j = -radius; j <= radius; ++j)
                excluded[(best + j + grid) % grid] = -1.;
        }
    }
    if (backward) fftwf_destroy_plan(backward);
    if (forward) fftwf_destroy_plan(forward);
    fftwf_free(scratch);
    return ready ? 0 : -1;
}
