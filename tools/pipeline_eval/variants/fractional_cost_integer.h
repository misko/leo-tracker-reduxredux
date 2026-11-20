#ifndef LEO_FRACTIONAL_COST_INTEGER_H
#define LEO_FRACTIONAL_COST_INTEGER_H

#if defined(__x86_64__) && (defined(__GNUC__) || defined(__clang__)) && \
    LEO_PRESENCE_PRECOMPUTE && !LEO_PRESENCE_ENERGY_SYMBOL_SUPPORT && \
    !LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY && LEO_PRESENCE_EPOCH_FRAMES == 16
#include <immintrin.h>

/* Each vector contains two independent complex correlations. Products and the
 * ordered addition of samples are the same binary64 operations per epoch. */
__attribute__((target("avx2,no-fma"), always_inline))
static inline __m256d leo_grid_add(__m256d accum, __m256d signal,
    __m256d swapped, __m256d real, __m256d imag)
{
    return _mm256_add_pd(accum,
        _mm256_addsub_pd(_mm256_mul_pd(signal, real), _mm256_mul_pd(swapped, imag)));
}

__attribute__((target("avx2,no-fma")))
static void leo_grid_correlate(const leo_presence_workspace *w, int start,
    double complex out[4][2][64])
{
    for (int s = 0; s < 64; ++s) {
        const int begin = symbol_start(w, s + 2), end = symbol_start(w, s + 3);
        __m256d exact0 = _mm256_setzero_pd(), exact1 = exact0;
        __m256d control0 = exact0, control1 = exact0;
        for (int k = begin; k < end; ++k) {
            __m256d pair0, pair1;
            memcpy(&pair0, w->samples + start + k, sizeof(pair0));
            memcpy(&pair1, w->samples + start + k + 3, sizeof(pair1));
            __m256d swap0 = _mm256_permute_pd(pair0, 0x5), swap1 = _mm256_permute_pd(pair1, 0x5);
            const double complex e = w->glrt_exact_rotated[k], c = w->glrt_control_rotated[k];
            __m256d er = _mm256_set1_pd(creal(e)), ei = _mm256_set1_pd(cimag(e));
            __m256d cr = _mm256_set1_pd(creal(c)), ci = _mm256_set1_pd(cimag(c));
            exact0 = leo_grid_add(exact0, pair0, swap0, er, ei);
            exact1 = leo_grid_add(exact1, pair1, swap1, er, ei);
            control0 = leo_grid_add(control0, pair0, swap0, cr, ci);
            control1 = leo_grid_add(control1, pair1, swap1, cr, ci);
        }
        double complex pair[2];
        memcpy(pair, &exact0, sizeof(pair));
        out[0][0][s] = pair[0]; out[1][0][s] = pair[1];
        memcpy(pair, &exact1, sizeof(pair));
        out[2][0][s] = pair[0]; out[3][0][s] = pair[1];
        memcpy(pair, &control0, sizeof(pair));
        out[0][1][s] = pair[0]; out[1][1][s] = pair[1];
        memcpy(pair, &control1, sizeof(pair));
        out[2][1][s] = pair[0]; out[3][1][s] = pair[1];
    }
}

/* The already scored central hypothesis used identical integer support,
 * cfo and templates. The other four share its rotation setup but keep
 * independent FFTs, frame ceilings and reduction order. */
static int leo_grid_four(leo_presence_workspace *w, size_t count, int center,
    double cfo, double exact, double control, double result[5][3])
{
    if (!w->wide_regional || count != 200000 || w->rate != 10000000 ||
        w->n != 13333 || w->acquisition_first_frame != 0 || center < 2 ||
        center > (int)w->n - 3 || !__builtin_cpu_supports("avx2")) return 0;
    int start[LEO_PRESENCE_EPOCH_FRAMES], used = 0;
    const int end = symbol_start(w, 66);
    for (int f = 0; f < LEO_PRESENCE_EPOCH_FRAMES; ++f) {
        int low = frame_start(w, center - 2, f);
        int high = frame_start(w, center + 2, f);
        if (low + end > (int)count) break;
        if (high + end > (int)count || high - low != 4) return 0;
        start[used++] = low;
    }
    glrt_prepare_rotations(w, cfo, 0, 0);
    result[2][0] = exact;
    result[2][1] = control;
    double spectra[4][2][128] = {{{0}}}, ceilings[4][2] = {{0}};
    for (int f = 0; f < used; ++f) {
        double complex correlation[4][2][64];
        leo_grid_correlate(w, start[f], correlation);
        for (int q = 0; q < 4; ++q)
            glrt_add_frame(w, correlation[q], spectra[q], ceilings[q]);
    }
    for (int q = 0; q < 4; ++q) glrt_finish(w, spectra[q], ceilings[q], result[q + (q >= 2)]);
    return 1;
}

#else
static int leo_grid_four(leo_presence_workspace *w, size_t count, int center,
    double cfo, double exact, double control, double result[5][3])
{
    (void)w; (void)count; (void)center; (void)cfo; (void)result;
    (void)exact; (void)control;
    return 0;
}
#endif
#endif
