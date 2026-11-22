#include <immintrin.h>

/* A vector holds two neighboring epochs with interleaved real and imaginary parts. */
__attribute__((target("avx2,fma")))
static inline __m256d stencil_multiply(__m256d a, __m256d b)
{
    __m256d cross = _mm256_mul_pd(_mm256_permute_pd(a, 15), _mm256_permute_pd(b, 5));
    return _mm256_fmaddsub_pd(_mm256_movedup_pd(a), b, cross);
}

__attribute__((target("avx2,fma")))
static inline void stencil_tap(const IqSample *iq, const complex64x2 *phase,
                               const complex64x2 *exact, __m256d *left, __m256d *right)
{
    __m256d rotation = _mm256_broadcast_pd((const __m128d *)phase);
    __m256d reference = _mm256_broadcast_pd((const __m128d *)exact);
    __m256d a = _mm256_loadu_pd((const double *)iq);
    __m256d b = _mm256_loadu_pd((const double *)(iq + 2));
    *left = stencil_multiply(reference, stencil_multiply(a, rotation));
    *right = stencil_multiply(reference, stencil_multiply(b, rotation));
}

__attribute__((target("avx2,fma")))
static inline __m256d stencil_sum(const __m256d values[lanes])
{
    return _mm256_add_pd(_mm256_add_pd(values[0], values[1]),
                         _mm256_add_pd(values[2], values[3]));
}

__attribute__((target("avx2,fma")))
void correlated_stencil(const IqSample *restrict iq, const int32_t *restrict starts, int frames,
                        const complex64x2 *restrict phase, const complex64x2 *restrict exact,
                        complex64x2 out[restrict 4][15 * symbols])
{
    for (int f = 0; f < frames; ++f) {
        const IqSample *received = iq + starts[f];
        for (int s = 0; s < symbols; ++s) {
            int k = s * taps;
            __m256d left[lanes], right[lanes];
            for (int i = 0; i < lanes; ++i)
                stencil_tap(received + k + i, phase + k + i, exact + k + i, &left[i], &right[i]);
            for (int t = lanes; t < taps; t += lanes) {
                for (int i = 0; i < lanes; ++i) {
                    int index = k + t + i;
                    __m256d a, b;
                    stencil_tap(received + index, phase + index, exact + index, &a, &b);
                    left[i] = _mm256_add_pd(left[i], a);
                    right[i] = _mm256_add_pd(right[i], b);
                }
            }
            __m256d a = stencil_sum(left), b = stencil_sum(right);
            int index = f * symbols + s;
            _mm_storeu_pd((double *)&out[0][index], _mm256_castpd256_pd128(a));
            _mm_storeu_pd((double *)&out[1][index], _mm256_extractf128_pd(a, 1));
            _mm_storeu_pd((double *)&out[2][index], _mm256_castpd256_pd128(b));
            _mm_storeu_pd((double *)&out[3][index], _mm256_extractf128_pd(b, 1));
        }
    }
}
