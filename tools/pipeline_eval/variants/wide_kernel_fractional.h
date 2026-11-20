#ifndef LEO_WIDE_KERNEL_FRACTIONAL_H
#define LEO_WIDE_KERNEL_FRACTIONAL_H

#if defined(__SSE2__) && (defined(__GNUC__) || defined(__clang__)) && defined(__x86_64__)
#include <immintrin.h>

#if defined(LEO_WIDE_KERNEL_TRACE)
static uint64_t wide_kernel_counts[3];

/* Diagnostic builds alone expose ABI-side telemetry. */
void leo_wide_kernel_fractional_counts(uint64_t out[3])
{
    memcpy(out,wide_kernel_counts,sizeof(wide_kernel_counts));
    memset(wide_kernel_counts,0,sizeof(wide_kernel_counts));
}
#define LEO_WIDE_KERNEL_COUNT(slot,amount) (wide_kernel_counts[(slot)] += (amount))
#else
#define LEO_WIDE_KERNEL_COUNT(slot,amount) ((void)0)
#endif

/* Each vector holds two independent complex outputs. All taps advance in the
 * scalar order, and dividing retains the scalar SSE2 rounding point. */
__attribute__((target("avx2,no-fma")))
static void leo_wide_fractional_block(const leo_fractional_runtime *filter,
    const double complex *in, int size, double complex *out)
{
    const __m256d norm = _mm256_set1_pd(filter->normalizer);
    int k = 0;
    for (; k + 4 <= size; k += 4) {
        __m256d even = _mm256_setzero_pd(), odd = even;
        for (int tap = 0; tap < 16; ++tap) {
            const __m256d weight = _mm256_broadcast_pd(filter->taps + tap);
            __m256d a, b;
            memcpy(&a,in+k+tap,sizeof(a));
            memcpy(&b,in+k+tap+2,sizeof(b));
            even = _mm256_add_pd(even,_mm256_mul_pd(weight,a));
            odd = _mm256_add_pd(odd,_mm256_mul_pd(weight,b));
        }
        even = _mm256_div_pd(even,norm);
        odd = _mm256_div_pd(odd,norm);
        memcpy(out+k,&even,sizeof(even));
        memcpy(out+k+2,&odd,sizeof(odd));
    }
    LEO_WIDE_KERNEL_COUNT(0,k);
    for (; k < size; ++k)
        out[k] = leo_fractional_runtime_dot(filter,in+k);
    LEO_WIDE_KERNEL_COUNT(1,size%4);
}
#define LEO_WIDE_KERNEL_AVX2 1
#endif

#endif
