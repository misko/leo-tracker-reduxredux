#include <immintrin.h>

/* The pinned generic x86-64 reduction has four Float32 chains. The low
   and high 128-bit halves below hold the corresponding chains for two
   independent partners of the same normalized frame. */
static inline Sample covariance_dot(const Sample *a, const Sample *b, int width)
{
    float re = 0.f, im = 0.f;
#pragma omp simd reduction(+ : re, im)
    for (int i = 0; i < width; ++i) {
        re += a[i].re * b[i].re + a[i].im * b[i].im;
        im += a[i].im * b[i].re - a[i].re * b[i].im;
    }
    return (Sample){re, im};
}

__attribute__((target("avx2")))
static void covariance_two(const Sample *a, const Sample *b, const Sample *c, int width, Sample out[2])
{
    __m256 real = _mm256_setzero_ps(), imag = _mm256_setzero_ps();
    int i = 0;
    for (; i + 3 < width; i += 4) {
        __m256 x = _mm256_broadcast_ps((const __m128 *)(a + i));
        __m256 y = _mm256_broadcast_ps((const __m128 *)(a + i + 2));
        __m256 b0 = _mm256_set_m128(_mm_loadu_ps((const float *)(c + i)),
                                     _mm_loadu_ps((const float *)(b + i)));
        __m256 b1 = _mm256_set_m128(_mm_loadu_ps((const float *)(c + i + 2)),
                                     _mm_loadu_ps((const float *)(b + i + 2)));
        __m256 ar = _mm256_shuffle_ps(x, y, _MM_SHUFFLE(2, 0, 2, 0));
        __m256 ai = _mm256_shuffle_ps(x, y, _MM_SHUFFLE(3, 1, 3, 1));
        __m256 br = _mm256_shuffle_ps(b0, b1, _MM_SHUFFLE(2, 0, 2, 0));
        __m256 bi = _mm256_shuffle_ps(b0, b1, _MM_SHUFFLE(3, 1, 3, 1));
        real = _mm256_add_ps(real, _mm256_add_ps(_mm256_mul_ps(ar, br), _mm256_mul_ps(ai, bi)));
        imag = _mm256_add_ps(imag, _mm256_sub_ps(_mm256_mul_ps(ai, br), _mm256_mul_ps(ar, bi)));
    }
    float re[8], im[8];
    _mm256_storeu_ps(re, real);
    _mm256_storeu_ps(im, imag);
    for (; i < width; ++i) {
        re[0] += a[i].re * b[i].re + a[i].im * b[i].im;
        im[0] += a[i].im * b[i].re - a[i].re * b[i].im;
        re[4] += a[i].re * c[i].re + a[i].im * c[i].im;
        im[4] += a[i].im * c[i].re - a[i].re * c[i].im;
    }
    for (int partner = 0; partner < 2; ++partner) {
        float r = 0.f, j = 0.f;
        for (int lane = 4 * partner; lane < 4 * partner + 4; ++lane) {
            r += re[lane];
            j += im[lane];
        }
        out[partner] = (Sample){r, j};
    }
}

void experimental_covariance_dots(const Sample *a, const Sample *b, const Sample *c,
                                  int width, int packed, Sample out[2])
{
    if (packed && __builtin_cpu_supports("avx2")) {
        covariance_two(a, b, c, width, out);
    } else {
        out[0] = covariance_dot(a, b, width);
        out[1] = covariance_dot(a, c, width);
    }
}

static inline void store_covariance(double complex matrix[count][count], int f, int other, Sample value)
{
    matrix[f][other] = value.re + I * value.im;
    matrix[other][f] = value.re - I * value.im;
}
