/* Int8 reconstruction of a 20-direction complex pilot basis on AVX-VNNI. */
#include <immintrin.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>

enum { rank_groups = 10, max_tile = 512 };

static __m128i byte_pairs(__m256 x, __m256 scale, __m256 offset)
{
    __m256i rounded = _mm256_cvtps_epi32(_mm256_fmadd_ps(x, scale, offset));
    __m128i words = _mm_packs_epi32(_mm256_castsi256_si128(rounded),
                                   _mm256_extracti128_si256(rounded, 1));
    return _mm_packus_epi16(words, words);
}

void fold_integer_basis(const float *basis, int stride, int tile, float scale,
    const int32_t *coefficients, const int32_t *bias, const float *coef_norm,
    const float *normalization, int first, int valid, const int32_t *anchors, int anchor_count,
    int lanes, const int32_t *frames, int frame_count, int epochs, double *scores)
{
    if (tile > max_tile || tile < 1) return;
    uint32_t packed[rank_groups][max_tile];
    __m256 step = _mm256_set1_ps(scale), offset = _mm256_set1_ps(128.0f);
    for (int group = 0; group < rank_groups; ++group) {
        const float *a = basis + 4 * (size_t)group * stride;
        const float *b = a + 2 * stride;
        int t = 0;
        for (; t + 3 < tile; t += 4) {
            __m128i re = byte_pairs(_mm256_loadu_ps(a + 2*t), step, offset);
            __m128i im = byte_pairs(_mm256_loadu_ps(b + 2*t), step, offset);
            _mm_storeu_si128((__m128i *)(packed[group] + t), _mm_unpacklo_epi16(re, im));
        }
        for (; t < tile; ++t) {
            uint32_t aa = (uint32_t)lrintf(a[2*t] * scale + 128.0f);
            uint32_t ab = (uint32_t)lrintf(a[2*t+1] * scale + 128.0f);
            uint32_t ba = (uint32_t)lrintf(b[2*t] * scale + 128.0f);
            uint32_t bb = (uint32_t)lrintf(b[2*t+1] * scale + 128.0f);
            packed[group][t] = aa | (ab << 8) | (ba << 16) | (bb << 24);
        }
    }
    const int last = first + tile;
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        for (int frame = 0; frame < frame_count; ++frame) {
            const int base = anchors[anchor] + frames[frame];
            const int lo = first > base ? first : base;
            const int remaining = valid < base + epochs ? valid : base + epochs;
            const int hi = last < remaining ? last : remaining;
            if (lo >= hi) continue;
            for (int lane = 0; lane < lanes; ++lane) {
                const int filter = anchor * lanes + lane;
                const int32_t *cr = coefficients + 2 * rank_groups * filter;
                const int32_t *ci = cr + rank_groups;
                double *score = scores + (size_t)lane * epochs;
                const float norm = coef_norm[filter] / scale;
                int t = lo;
                for (; t + 7 < hi; t += 8) {
                    __m256i real = _mm256_set1_epi32(bias[2 * filter]);
                    __m256i imag = _mm256_set1_epi32(bias[2 * filter + 1]);
                    #pragma GCC unroll 10
                    for (int g = 0; g < rank_groups; ++g) {
                        __m256i input = _mm256_loadu_si256((__m256i *)(packed[g] + t - first));
                        real = _mm256_dpbusd_avx_epi32(real, input, _mm256_set1_epi32(cr[g]));
                        imag = _mm256_dpbusd_avx_epi32(imag, input, _mm256_set1_epi32(ci[g]));
                    }
                    __m256 re = _mm256_cvtepi32_ps(real), im = _mm256_cvtepi32_ps(imag);
                    __m256 magnitude = _mm256_sqrt_ps(_mm256_fmadd_ps(re, re, _mm256_mul_ps(im, im)));
                    __m256 value = _mm256_mul_ps(magnitude, _mm256_mul_ps(_mm256_set1_ps(norm),
                                                   _mm256_loadu_ps(normalization + t)));
                    double *ptr = score + t - base;
                    __m256d low = _mm256_cvtps_pd(_mm256_castps256_ps128(value));
                    __m256d high = _mm256_cvtps_pd(_mm256_extractf128_ps(value, 1));
                    _mm256_storeu_pd(ptr, _mm256_add_pd(_mm256_loadu_pd(ptr), low));
                    _mm256_storeu_pd(ptr+4, _mm256_add_pd(_mm256_loadu_pd(ptr+4), high));
                }
                for (; t < hi; ++t) {
                    int32_t re = bias[2 * filter], im = bias[2 * filter + 1];
                    for (int g = 0; g < rank_groups; ++g) {
                        uint32_t input = packed[g][t - first];
                        uint32_t rc = (uint32_t)cr[g], ic = (uint32_t)ci[g];
                        for (int j = 0; j < 4; ++j) {
                            re += (int)(input & 255) * (int8_t)(rc & 255);
                            im += (int)(input & 255) * (int8_t)(ic & 255);
                            input >>= 8;
                            rc >>= 8;
                            ic >>= 8;
                        }
                    }
                    score[t - base] += sqrtf((float)re * re + (float)im * im) * norm * normalization[t];
                }
            }
        }
    }
}
