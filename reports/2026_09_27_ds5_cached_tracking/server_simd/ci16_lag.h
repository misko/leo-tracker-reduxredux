/* Exact x86 SIMD extension of the pinned deployment ci16_lag.h. */
#include <complex.h>
#include <stddef.h>
#include <stdint.h>

#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("ssse3,sse4.1")))
static inline void server_lag_four(const int16_t *a_iq, const int16_t *b_iq,
    int64_t sums[4][4])
{
    __m128i a=_mm_loadu_si128((const __m128i *)a_iq);
    __m128i b=_mm_loadu_si128((const __m128i *)b_iq);
    __m128i ar=server_deinterleave_real32(a), ai=server_deinterleave_imag32(a);
    __m128i br=server_deinterleave_real32(b), bi=server_deinterleave_imag32(b);
    __m128i products[4]={_mm_mullo_epi32(ar,br),_mm_mullo_epi32(ai,bi),
        _mm_mullo_epi32(ar,bi),_mm_mullo_epi32(ai,br)};
    for (int product=0; product<4; ++product) {
        __m128i lo=_mm_cvtepi32_epi64(products[product]);
        __m128i hi=_mm_cvtepi32_epi64(_mm_srli_si128(products[product],8));
        _mm_storeu_si128((__m128i *)sums[product],
            _mm_add_epi64(_mm_loadu_si128((const __m128i *)sums[product]),lo));
        _mm_storeu_si128((__m128i *)(sums[product]+2),
            _mm_add_epi64(_mm_loadu_si128((const __m128i *)(sums[product]+2)),hi));
    }
}
#endif

static double complex ci16_lag_sum(const int16_t *iq, size_t count, size_t lag)
{
    size_t k=0, end=count-lag;
    int64_t real=0, imag=0;
#if defined(__x86_64__) || defined(__i386__)
    if (server_simd_enabled()) {
        int64_t sums[4][4]={{0}};
        for (; k+3<end; k+=4) server_lag_four(iq+2*k,iq+2*(k+lag),sums);
        for (int lane=0; lane<4; ++lane) {
            real+=sums[0][lane]+sums[1][lane];
            imag+=sums[2][lane]-sums[3][lane];
        }
    }
#endif
    for (; k<end; ++k) {
        int64_t ar=iq[2*k], ai=iq[2*k+1], br=iq[2*(k+lag)], bi=iq[2*(k+lag)+1];
        real+=ar*br+ai*bi; imag+=ar*bi-ai*br;
    }
    return (double)real+I*(double)imag;
}
