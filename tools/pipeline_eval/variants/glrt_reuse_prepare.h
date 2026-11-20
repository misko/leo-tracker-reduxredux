#ifndef LEO_GLRT_WIDE_DUAL_PREPARE_H
#define LEO_GLRT_WIDE_DUAL_PREPARE_H

#if defined(__x86_64__) && (defined(__GNUC__) || defined(__clang__))
#include <immintrin.h>

#define LEO_GLRT_WIDE_DUAL_PREPARE 1

/* The fixed wide visit is smaller than 2^18 CI16 sample times. A receiver's
 * energy quantum is an integer <= 2^31 and its prefix is therefore < 2^49.
 * Conversion through binary64's exponent bias is exact throughout that range. */
__attribute__((target("avx2,no-fma")))
static int leo_prepare_wide_pair(leo_dwell_input *d,const int16_t *ci16,size_t count)
{
    if (!ci16 || !count || count >= (1u << 18) || (count & 1) ||
        leo_dwell_input_reserve(d,count)) return -1;
    const __m256i receiver_order = _mm256_setr_epi32(0,1,4,5,2,3,6,7);
    const __m256 norm = _mm256_set1_ps(0x1p-15f);
    const __m128d bias = _mm_set1_pd(0x1p52);
    const __m128i bias_bits = _mm_castpd_si128(bias);
    const __m128d scale = _mm_set1_pd(0x1p-30);
    __m128i total = _mm_setzero_si128();
    d->count = count;
    d->prefix[0][0] = d->prefix[1][0] = 0;
    for (size_t i = 0; i < count; i += 2) {
        __m128i packed;
        memcpy(&packed,ci16+4*i,sizeof(packed));
        const __m256i separated = _mm256_permutevar8x32_epi32(
            _mm256_cvtepi16_epi32(packed),receiver_order);
        const __m256d raw0 = _mm256_cvtepi32_pd(_mm256_castsi256_si128(separated));
        const __m256d raw1 = _mm256_cvtepi32_pd(_mm256_extracti128_si256(separated,1));
        memcpy(d->raw[0]+i,&raw0,sizeof(raw0));
        memcpy(d->raw[1]+i,&raw1,sizeof(raw1));

        const __m256 normalized = _mm256_mul_ps(_mm256_cvtepi32_ps(separated),norm);
        _mm_storeu_ps(d->normalized[0]+2*i,_mm256_castps256_ps128(normalized));
        _mm_storeu_ps(d->normalized[1]+2*i,_mm256_extractf128_ps(normalized,1));

        /* (-32768)^2+(-32768)^2 has the unsigned 32-bit value 2^31. */
        const __m128i squares = _mm_madd_epi16(packed,packed);
        const __m128i first = _mm_add_epi64(total,_mm_cvtepu32_epi64(squares));
        total = _mm_add_epi64(first,_mm_cvtepu32_epi64(_mm_srli_si128(squares,8)));
        const __m128d earlier = _mm_mul_pd(
            _mm_sub_pd(_mm_castsi128_pd(_mm_or_si128(first,bias_bits)),bias),scale);
        const __m128d later = _mm_mul_pd(
            _mm_sub_pd(_mm_castsi128_pd(_mm_or_si128(total,bias_bits)),bias),scale);
        _mm_storeu_pd(d->prefix[0]+i+1,_mm_unpacklo_pd(earlier,later));
        _mm_storeu_pd(d->prefix[1]+i+1,_mm_unpackhi_pd(earlier,later));
    }
    return 0;
}
#endif

#endif
