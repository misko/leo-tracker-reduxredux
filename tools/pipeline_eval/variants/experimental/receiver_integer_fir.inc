/* This proposal FIR uses signed Q15 coefficients only in the quarter-rate
   scout. The full-rate refinement and original-sample verifier stay floating
   point. */
#include <immintrin.h>
#include <stdint.h>
#include <stdlib.h>

enum { q15_taps = 81, q15_half = 40, q15_scale = 32768 };

__attribute__((target("avx2")))
static void planar_iq(const float *x, int mixed, int16_t *real, int16_t *imag) {
    const __m256 scale = _mm256_set1_ps(mixed ? .5f : 1.f);
    const __m256i order = _mm256_setr_epi32(0, 1, 4, 5, 2, 3, 6, 7);
    for (int k = 0; k < samples; k += 8) {
        __m256 a = _mm256_mul_ps(_mm256_loadu_ps(x + 2 * k), scale);
        __m256 b = _mm256_mul_ps(_mm256_loadu_ps(x + 2 * k + 8), scale);
        __m256 xr = _mm256_shuffle_ps(a, b, _MM_SHUFFLE(2, 0, 2, 0));
        __m256 xi = _mm256_shuffle_ps(a, b, _MM_SHUFFLE(3, 1, 3, 1));
        __m256i ir = _mm256_cvtps_epi32(_mm256_permutevar8x32_ps(xr, order));
        __m256i ii = _mm256_cvtps_epi32(_mm256_permutevar8x32_ps(xi, order));
        _mm_storeu_si128((__m128i *)(real + k),
                         _mm_packs_epi32(_mm256_castsi256_si128(ir), _mm256_extracti128_si256(ir, 1)));
        _mm_storeu_si128((__m128i *)(imag + k),
                         _mm_packs_epi32(_mm256_castsi256_si128(ii), _mm256_extracti128_si256(ii, 1)));
    }
}

__attribute__((target("avx2,avxvnni")))
static void quantized_fir(const float *x, const float *coeff, const int16_t *weights,
                          int mixed, float *out) {
    int16_t real[samples], imag[samples];
    planar_iq(x, mixed, real, imag);
    __m256i weight[5];
    for (int k = 0; k < 5; ++k)
        weight[k] = _mm256_loadu_si256((const __m256i *)(weights + 16 * k));
    const float unscale = (mixed ? 2.f : 1.f) / q15_scale;
    for (int j = 0; j < samples / 4; ++j) {
        const int mid = 4 * j;
        if (mid < q15_half || mid + q15_half >= samples) {
            float re = x[2 * mid] * coeff[q15_half];
            float im = x[2 * mid + 1] * coeff[q15_half];
            for (int d = -q15_half; d <= q15_half; ++d) {
                if (d && mid + d >= 0 && mid + d < samples) {
                    re += coeff[q15_half + d] * x[2 * (mid + d)];
                    im += coeff[q15_half + d] * x[2 * (mid + d) + 1];
                }
            }
            out[2 * j] = re;
            out[2 * j + 1] = im;
            continue;
        }
        const int first = mid - q15_half;
        __m256i re = _mm256_setzero_si256(), im = _mm256_setzero_si256();
        for (int k = 0; k < 5; ++k) {
            const __m256i xr = _mm256_loadu_si256((const __m256i *)(real + first + 16 * k));
            const __m256i xi = _mm256_loadu_si256((const __m256i *)(imag + first + 16 * k));
            re = _mm256_dpwssd_avx_epi32(re, xr, weight[k]);
            im = _mm256_dpwssd_avx_epi32(im, xi, weight[k]);
        }
        /* Reduce each complex coordinate over contributing taps, then place
           real and imaginary sums in adjacent 32-bit lanes. */
        __m128i rs = _mm_add_epi32(_mm256_castsi256_si128(re), _mm256_extracti128_si256(re, 1));
        __m128i is = _mm_add_epi32(_mm256_castsi256_si128(im), _mm256_extracti128_si256(im, 1));
        __m128i sums = _mm_hadd_epi32(rs, is);
        sums = _mm_hadd_epi32(sums, sums);
        __m128i tail = _mm_setr_epi32(real[mid + q15_half] * weights[q15_taps - 1],
                                      imag[mid + q15_half] * weights[q15_taps - 1], 0, 0);
        __m128 result = _mm_mul_ps(_mm_cvtepi32_ps(_mm_add_epi32(sums, tail)), _mm_set1_ps(unscale));
        _mm_storel_pi((__m64 *)(out + 2 * j), result);
    }
}

/* x comes from the native lane loader. Its unmixed coordinates are exactly
   signed CI16; a rotated complex coordinate is bounded by sqrt(2)*32768
   and fits in int16 after scaling by 1/2. */
int delay_decimate_integer(const float *x, const float *coeff, int taps, int stride,
                           int mixed, float *out) {
    if (!x || !coeff || !out || taps != q15_taps || stride != 4 ||
        !__builtin_cpu_supports("avxvnni"))
        return delay_decimate(x, coeff, taps, stride, out);
    int16_t weights[q15_taps];
    int weight_l1 = 0;
    for (int k = 0; k < q15_taps; ++k) {
        float scaled = coeff[k] * q15_scale;
        if (!isfinite(scaled) || fabsf(scaled) > INT16_MAX || coeff[k] != coeff[q15_taps - 1 - k])
            return delay_decimate(x, coeff, taps, stride, out);
        int q = (int)lroundf(scaled);
        weights[k] = q;
        weight_l1 += abs(q);
    }
    /* One bound covers every partial sum and the finished dot product,
       including ADC clipping and the full negative int16 endpoint. */
    if (weight_l1 > INT32_MAX / q15_scale)
        return delay_decimate(x, coeff, taps, stride, out);
    quantized_fir(x, coeff, weights, mixed, out);
    return 0;
}
