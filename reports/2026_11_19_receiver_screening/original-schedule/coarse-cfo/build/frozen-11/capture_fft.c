/* In-process NumPy-to-C port for the frozen folded FFT bank. */
#include <complex.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef int32_t npy_intp, npy_int32;
typedef double complex npy_cdouble;
typedef struct {
    const npy_cdouble *samples, *references;
    const double *frequencies;
    const npy_intp *starts, *stops, *offsets;
    const double *prefix;
    double *scores;
    npy_int32 *support;
    int sample_count, cfo_count, symbol_count, offset_count;
    double sample_rate_hz;
    int epoch_count, fast_magnitude, invalid_geometry;
} FoldedAnchorGridKernel;

typedef struct {
    int fft_length, input_ffts, inverse_ffts, filter_ffts;
    size_t buffer_bytes;
} CaptureFftStats;

static _Thread_local CaptureFftStats *measurement;
static _Thread_local const float *mix;
static pthread_mutex_t planner = PTHREAD_MUTEX_INITIALIZER;

/* The measured body reports these same fields to the standalone runner.
 * Return them through the library port instead of logging from this worker. */
static int bank_stats(FILE *stream, const char *format, int size, int signal, int inverse,
                      int filters, size_t bytes) {
    (void)stream;
    (void)format;
    *measurement = (CaptureFftStats){size, signal, inverse, filters, bytes};
    return 0;
}

#define LEO_GRID_FUNCTION capture_fft_fold
#define fprintf bank_stats
#include "folded_bank.c"
#undef fprintf
#undef LEO_GRID_FUNCTION

int capture_fft_score_grid(
    const double complex *samples, int sample_count, const double complex *references,
    int reference_count, const double *frequencies, int cfo_count,
    const int32_t *starts, const int32_t *stops, int symbol_count,
    const int32_t *offsets, int offset_count, const double *prefix, double rate,
    int epochs, double *scores, int32_t *support, CaptureFftStats *stats, const float *weights
) {
    if (sample_count <= 0 || sample_count > 200000 || reference_count <= 0 ||
        reference_count > 200000 || cfo_count <= 0 || cfo_count > 21 ||
        symbol_count <= 0 || symbol_count > 22 || offset_count <= 0 || offset_count > 16 ||
        epochs <= 0 || epochs > 13333 || !isfinite(rate) || rate <= 0)
        return 1;
    for (int i = 0; i < cfo_count; ++i)
        if (!isfinite(frequencies[i])) return 1;
    for (int i = 0; i < symbol_count; ++i)
        if (starts[i] < 0 || stops[i] <= starts[i] || stops[i] > reference_count ||
            stops[i] - starts[i] > 64 || stops[i] - starts[i] > sample_count)
            return 1;
    for (int i = 0; i < offset_count; ++i)
        if (offsets[i] < 0 || offsets[i] > sample_count || (i && offsets[i] < offsets[i - 1]))
            return 1;
    for (int i = 0; i < sample_count; ++i)
        if (!(fabs(creal(samples[i])) <= 32768.0 && fabs(cimag(samples[i])) <= 32768.0))
            return 1;
    for (int i = 0; i < reference_count; ++i)
        if (!(fabs(creal(references[i])) <= 32768.0 && fabs(cimag(references[i])) <= 32768.0))
            return 1;
    FoldedAnchorGridKernel kernel = {
        .samples = samples, .references = references, .frequencies = frequencies,
        .starts = starts, .stops = stops, .offsets = offsets, .prefix = prefix,
        .scores = scores, .support = support, .sample_count = sample_count,
        .cfo_count = cfo_count, .symbol_count = symbol_count, .offset_count = offset_count,
        .sample_rate_hz = rate, .epoch_count = epochs, .fast_magnitude = 1,
    };
    memset(support, 0, (size_t)epochs * sizeof(*support));
    if (pthread_mutex_lock(&planner)) return 1;
    measurement = stats;
    mix = weights;
    capture_fft_fold(&kernel);
    measurement = NULL;
    mix = NULL;
    pthread_mutex_unlock(&planner);
    return kernel.invalid_geometry;
}
