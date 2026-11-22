/* Prepare four absolute oscillator arguments without changing their rounding. */
#include <fenv.h>
#include <immintrin.h>

static int absolute_phase_batch_supported(double cfo)
{
    /* The verifier covers bounded positive sample positions. This lower
     * bound keeps every nonzero intermediate in the normal double range. */
    if (!(fabs(cfo) >= 0x1p-700 && fabs(cfo) <= 5000000.) ||
        !__builtin_cpu_supports("avx2") || !__builtin_cpu_supports("fma")) return 0;
    const unsigned controls = _MM_ROUND_MASK | _MM_MASK_MASK | _MM_FLUSH_ZERO_MASK |
                              _MM_DENORMALS_ZERO_MASK;
    return (_mm_getcsr() & controls) == _MM_MASK_MASK && fegetround() == FE_TONEAREST;
}

/* 10^7 = 2^7 * 78125. In the bounded normal domain the initial quotient is
 * within a few ulps. The integer significand of the divisor has 17 bits,
 * so the cancellation in the first FMA leaves an exactly representable
 * residual. The exact quotient in ulp units has odd denominator 78125,
 * leaving at least 1 / (2 * 78125) ulp from a rounding midpoint. The
 * reciprocal error applied to the small residual is far below that gap. */
__attribute__((target("avx2,fma"), always_inline))
static inline __m256d divide_sample_rate(__m256d x)
{
    const __m256d rate = _mm256_set1_pd(10000000.);
    const __m256d reciprocal = _mm256_set1_pd(0x1.ad7f29abcaf48p-24);
    __m256d quotient = _mm256_mul_pd(x, reciprocal);
    __m256d residual = _mm256_fnmadd_pd(quotient, rate, x);
    return _mm256_fmadd_pd(residual, reciprocal, quotient);
}

__attribute__((target("avx2,fma")))
static void absolute_phase_batch(double *out, int begin, int count, double omega, double offset)
{
    __m256d integer = _mm256_setr_pd(begin, begin + 1, begin + 2, begin + 3);
    const __m256d angular = _mm256_set1_pd(omega);
    const __m256d fraction = _mm256_set1_pd(offset);
    for (int k = 0; k < count; k += 4) {
        __m256d position = _mm256_add_pd(integer, fraction);
        __m256d numerator = _mm256_mul_pd(angular, position);
        _mm256_storeu_pd(out + k, divide_sample_rate(numerator));
        integer = _mm256_add_pd(integer, _mm256_set1_pd(4.));
    }
}
