#ifndef LEO_NATIVE_HOTPATH_FOLD_H
#define LEO_NATIVE_HOTPATH_FOLD_H

#if defined(__x86_64__) && (defined(__GNUC__) || defined(__clang__))
#include <immintrin.h>

/* Four packed IQ times occupy two 16-byte vectors. Extract only the caller's
 * lane before converting the eight signed scalars to binary32. */
__attribute__((target("avx2,no-fma"), always_inline))
static inline __m256 native_hotpath_load(const int16_t *at, __m128i lane)
{
    __m128i a = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)at), lane);
    __m128i b = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(at + 8)), lane);
    return _mm256_cvtepi32_ps(_mm256_cvtepi16_epi32(_mm_unpacklo_epi64(a, b)));
}

/* Each epoch still accumulates frames in their original order. A scalar tail
 * handles unequal valid extents without reading any extra CI16 values. */
__attribute__((target("avx2,no-fma")))
static size_t native_hotpath_fold4(fftwf_complex *out[3], const int16_t *raw,
    size_t start, size_t off, const size_t valid[3], int rx)
{
    size_t common = valid[0] < valid[1] ? valid[0] : valid[1];
    if (valid[2] < common) common = valid[2];
    int b = 4 * rx;
    __m128i lane = _mm_setr_epi8(b, b + 1, b + 2, b + 3,
        b + 8, b + 9, b + 10, b + 11, -1, -1, -1, -1, -1, -1, -1, -1);
    size_t k = 0;
    for (; k + 4 <= common; k += 4) {
        const int16_t *at = raw + 4 * (start + off + k);
        __m256 a = native_hotpath_load(at, lane);
        __m256 a_swapped = _mm256_permute_ps(a, 0xb1);
        for (int m = 0; m < 3; ++m) {
            __m256 q = native_hotpath_load(at + 4 * (size_t)lags[m], lane);
            __m256 p = _mm256_mul_ps(a, _mm256_moveldup_ps(q));
            __m256 s = _mm256_mul_ps(a_swapped, _mm256_movehdup_ps(q));
            __m256 product = _mm256_blend_ps(_mm256_add_ps(p, s), _mm256_sub_ps(s, p), 0xaa);
            float *target = (float *)(out[m] + k);
            _mm256_storeu_ps(target, _mm256_add_ps(_mm256_loadu_ps(target), product));
        }
    }
    return k;
}
#define LEO_NATIVE_HOTPATH_AVX2 1
#endif

#endif
