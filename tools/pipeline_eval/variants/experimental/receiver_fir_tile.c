/* Reuse identical input vectors across four adjacent stride-four FIR outputs. */
#include <immintrin.h>
#include <stdint.h>

enum { input_samples = 200000, stride_four = 4, radius = 40 };

__attribute__((visibility("hidden")))
int leo_pgo_delay_decimate(const float *, const float *, int, int, float *);

__attribute__((target("avx2")))
static inline __m256 load_reverse(const float *in, __m256i reverse_pairs) {
    return _mm256_permutevar8x32_ps(_mm256_loadu_ps(in), reverse_pairs);
}

__attribute__((target("avx2")))
static inline __m256 accumulate(__m256 total, __m256 left, __m256 right, __m256 weight) {
    return _mm256_add_ps(total, _mm256_mul_ps(weight, _mm256_add_ps(left, right)));
}

__attribute__((target("avx2")))
static inline void emit(float *out, const float *center, float weight, __m256 sums) {
    __m128 low = _mm256_castps256_ps128(sums), high = _mm256_extractf128_ps(sums, 1);
    __m128 value = _mm_mul_ps(_mm_loadl_pi(_mm_setzero_ps(), (const __m64 *)center), _mm_set1_ps(weight));
    value = _mm_add_ps(value, low);
    value = _mm_add_ps(value, _mm_movehl_ps(low, low));
    value = _mm_add_ps(value, high);
    value = _mm_add_ps(value, _mm_movehl_ps(high, high));
    _mm_storel_pi((__m64 *)out, value);
}

static void edge_output(const float *in, const float *coeff, float *out, int j) {
    const int center = stride_four * j;
    float re = in[2 * center] * coeff[radius], im = in[2 * center + 1] * coeff[radius];
    for (int d = -radius; d <= radius; ++d) {
        int at = center + d;
        if (d && at >= 0 && at < input_samples) {
            re += coeff[radius + d] * in[2 * at];
            im += coeff[radius + d] * in[2 * at + 1];
        }
    }
    out[2 * j] = re;
    out[2 * j + 1] = im;
}

__attribute__((target("avx2")))
static void tiled_fir(const float *in, const float *coeff, float *out) {
    enum { output_samples = input_samples / stride_four, pad = radius / stride_four };
    __m256 weight[10];
    for (int k = 0; k < 10; ++k) {
        const float *c = coeff + radius + 1 + 4 * k;
        weight[k] = _mm256_setr_ps(c[0], c[0], c[1], c[1], c[2], c[2], c[3], c[3]);
    }
    const __m256i reverse_pairs = _mm256_setr_epi32(6, 7, 4, 5, 2, 3, 0, 1);
    for (int j = 0; j < pad; ++j)
        edge_output(in, coeff, out, j);
    for (int j = pad; j < output_samples - pad; j += 4) {
        const float *center = in + 2 * stride_four * j;
        const float *left = center - 8, *right = center + 2;
        __m256 l0 = load_reverse(left, reverse_pairs);
        __m256 l1 = load_reverse(left + 8, reverse_pairs);
        __m256 l2 = load_reverse(left + 16, reverse_pairs);
        __m256 l3 = load_reverse(left + 24, reverse_pairs);
        __m256 r0 = _mm256_loadu_ps(right), r1 = _mm256_loadu_ps(right + 8);
        __m256 r2 = _mm256_loadu_ps(right + 16), r3 = _mm256_loadu_ps(right + 24);
        __m256 a0 = accumulate(_mm256_setzero_ps(), l0, r0, weight[0]);
        __m256 a1 = accumulate(_mm256_setzero_ps(), l1, r1, weight[0]);
        __m256 a2 = accumulate(_mm256_setzero_ps(), l2, r2, weight[0]);
        __m256 a3 = accumulate(_mm256_setzero_ps(), l3, r3, weight[0]);
#pragma GCC unroll 9
        for (int k = 1; k < 10; ++k) {
            l3 = l2;
            l2 = l1;
            l1 = l0;
            l0 = load_reverse(left - 8 * k, reverse_pairs);
            r0 = r1;
            r1 = r2;
            r2 = r3;
            r3 = _mm256_loadu_ps(right + 24 + 8 * k);
            a0 = accumulate(a0, l0, r0, weight[k]);
            a1 = accumulate(a1, l1, r1, weight[k]);
            a2 = accumulate(a2, l2, r2, weight[k]);
            a3 = accumulate(a3, l3, r3, weight[k]);
        }
        emit(out + 2 * j, center, coeff[radius], a0);
        emit(out + 2 * j + 2, center + 8, coeff[radius], a1);
        emit(out + 2 * j + 4, center + 16, coeff[radius], a2);
        emit(out + 2 * j + 6, center + 24, coeff[radius], a3);
    }
    for (int j = output_samples - pad; j < output_samples; ++j)
        edge_output(in, coeff, out, j);
}

static int overlaps(const void *a, uintptr_t a_length, const void *b, uintptr_t b_length) {
    uintptr_t first = (uintptr_t)a, second = (uintptr_t)b;
    return first <= second ? second - first < a_length : first - second < b_length;
}

int delay_decimate(const float *in, const float *coeff, int taps, int stride, float *out) {
    const uintptr_t output_bytes = 2 * (input_samples / stride_four) * sizeof(float);
    if (!in || !coeff || !out || taps != 81 || stride != stride_four || !__builtin_cpu_supports("avx2") ||
        overlaps(in, 2 * input_samples * sizeof(float), out, output_bytes) ||
        overlaps(coeff, 81 * sizeof(float), out, output_bytes))
        return leo_pgo_delay_decimate(in, coeff, taps, stride, out);
    tiled_fir(in, coeff, out);
    return 0;
}
