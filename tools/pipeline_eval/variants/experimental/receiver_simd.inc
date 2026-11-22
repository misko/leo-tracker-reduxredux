/* The nominal 81-tap FIR accumulates four independent chains, as the x86-64
   release's OpenMP SIMD reduction does. Here each chain holds adjacent I/Q. */
#include <immintrin.h>

__attribute__((target("avx2")))
static int paired_fir(const float *x, const float *coeff, int taps, int stride, float *out) {
    if (taps != 81 || stride != 4 || !__builtin_cpu_supports("avx2")) return 0;
    const int half = 40;
    __m256 weights[10];
    for (int k = 0; k < 10; ++k) {
        const float *c = coeff + half + 1 + 4 * k;
        weights[k] = _mm256_setr_ps(c[0], c[0], c[1], c[1], c[2], c[2], c[3], c[3]);
    }
    __m256i reverse_pairs = _mm256_setr_epi32(6, 7, 4, 5, 2, 3, 0, 1);
    for (int j = 0; j < samples / stride; ++j) {
        int mid = j * stride;
        float re = x[2 * mid] * coeff[half];
        float im = x[2 * mid + 1] * coeff[half];
        if (mid >= half && mid + half < samples) {
            __m256 acc = _mm256_setzero_ps();
            for (int k = 0; k < 10; ++k) {
                int d = 1 + 4 * k;
                __m256 left = _mm256_loadu_ps(x + 2 * (mid - d - 3));
                __m256 right = _mm256_loadu_ps(x + 2 * (mid + d));
                left = _mm256_permutevar8x32_ps(left, reverse_pairs);
                acc = _mm256_add_ps(acc, _mm256_mul_ps(weights[k], _mm256_add_ps(left, right)));
            }
            float lanes[8];
            _mm256_storeu_ps(lanes, acc);
            for (int k = 0; k < 4; ++k) {
                re += lanes[2 * k];
                im += lanes[2 * k + 1];
            }
        } else {
            for (int d = -half; d <= half; ++d) {
                if (d && mid + d >= 0 && mid + d < samples) {
                    re += coeff[half + d] * x[2 * (mid + d)];
                    im += coeff[half + d] * x[2 * (mid + d) + 1];
                }
            }
        }
        out[2 * j] = re;
        out[2 * j + 1] = im;
    }
    return 1;
}

typedef struct { __m256 real, imag; } PackedRotation;
typedef struct { float real, imag, power; } LateCorrelation;

__attribute__((target("avx2")))
static void pack_rotation(const float *hr, const float *hi, PackedRotation *out, int count) {
    for (int j = 0; j < count; j += 4) {
        out[j / 4].real = _mm256_setr_ps(hr[j], hr[j], hr[j + 1], hr[j + 1],
                                        hr[j + 2], hr[j + 2], hr[j + 3], hr[j + 3]);
        out[j / 4].imag = _mm256_setr_ps(hi[j], hi[j], hi[j + 1], hi[j + 1],
                                        hi[j + 2], hi[j + 2], hi[j + 3], hi[j + 3]);
    }
}

/* Compute the same four sequential sums in an interleaved register layout. */
__attribute__((target("avx2")))
static void correlate_block(const float *x, const PackedRotation *rotation,
                            int count, float *a, float *c, float *power) {
    __m256 z = _mm256_setzero_ps();
    __m128 e = _mm_setzero_ps();
    for (int j = 0; j < count; j += 4) {
        __m256 iq = _mm256_loadu_ps(x + 2 * j);
        __m256 swapped = _mm256_permute_ps(iq, _MM_SHUFFLE(2, 3, 0, 1));
        __m256 real = _mm256_mul_ps(iq, rotation[j / 4].real);
        __m256 imag = _mm256_mul_ps(swapped, rotation[j / 4].imag);
        z = _mm256_add_ps(z, _mm256_addsub_ps(real, imag));
        __m256 squares = _mm256_mul_ps(iq, iq);
        __m256 pairs = _mm256_hadd_ps(squares, squares);
        __m128 low = _mm256_castps256_ps128(pairs), high = _mm256_extractf128_ps(pairs, 1);
        e = _mm_add_ps(e, _mm_shuffle_ps(low, high, _MM_SHUFFLE(1, 0, 1, 0)));
    }
    float zl[8], el[4];
    _mm256_storeu_ps(zl, z);
    _mm_storeu_ps(el, e);
    for (int k = 0; k < 4; ++k) {
        *a += zl[2 * k];
        *c += zl[2 * k + 1];
        *power += el[k];
    }
}

/* The released compiler accumulates later blocks serially. Each SIMD lane here
   handles a separate timing offset and keeps that per-sample addition order. */
__attribute__((target("avx2")))
static void correlate_late(const float *x, const float *hr, const float *hi, int start_epoch,
                           LateCorrelation out[9][frames][4]) {
    const int starts[] = {0, 4, 5};
    for (int batch = 0; batch < 3; ++batch) {
        const int first = starts[batch];
        for (int f = 0; f < frames; ++f) {
            const int offset = (40000 * f + 1) / 3 + 88 + start_epoch + first;
            for (int b = 0; b < 4; ++b) {
                const int begin = (b + 4) * block, end = begin + block;
                __m256 z = _mm256_setzero_ps();
                __m128 e = _mm_setzero_ps();
                for (int j = begin; j < end; ++j) {
                    __m256 iq = _mm256_loadu_ps(x + 2 * (offset + j));
                    __m256 swapped = _mm256_permute_ps(iq, _MM_SHUFFLE(2, 3, 0, 1));
                    __m256 real = _mm256_mul_ps(iq, _mm256_set1_ps(hr[j]));
                    __m256 imag = _mm256_mul_ps(swapped, _mm256_set1_ps(hi[j]));
                    z = _mm256_add_ps(z, _mm256_addsub_ps(real, imag));
                    __m256 squares = _mm256_mul_ps(iq, iq);
                    __m256 pairs = _mm256_hadd_ps(squares, squares);
                    __m128 low = _mm256_castps256_ps128(pairs), high = _mm256_extractf128_ps(pairs, 1);
                    e = _mm_add_ps(e, _mm_shuffle_ps(low, high, _MM_SHUFFLE(1, 0, 1, 0)));
                }
                float zl[8], el[4];
                _mm256_storeu_ps(zl, z);
                _mm_storeu_ps(el, e);
                for (int k = 0; k < 4; ++k)
                    out[first + k][f][b] = (LateCorrelation){zl[2 * k], zl[2 * k + 1], el[k]};
            }
        }
    }
}
