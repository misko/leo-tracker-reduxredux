#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if (defined(__x86_64__) || defined(__i386__)) && defined(__GNUC__)
#include <tmmintrin.h>
#define HAVE_SSSE3 1
#endif

static unsigned magnitude(uint8_t value)
{
    return value <= 128 ? value : 256 - value;
}

static size_t filter_differences(const uint8_t *row, const uint8_t *above,
                                 size_t size, uint8_t *sub, uint8_t *up)
{
    size_t i = 0;
    size_t sub_score = 0;
    size_t up_score = 0;
    for (; i < 4; i++) {
        sub[i] = row[i];
        up[i] = (uint8_t)(row[i] - above[i]);
        sub_score += magnitude(sub[i]);
        up_score += magnitude(up[i]);
    }
    for (; i < size; i++) {
        sub[i] = (uint8_t)(row[i] - row[i - 4]);
        up[i] = (uint8_t)(row[i] - above[i]);
        sub_score += magnitude(sub[i]);
        up_score += magnitude(up[i]);
    }
    return up_score < sub_score;
}

#if HAVE_SSSE3
__attribute__((target("ssse3")))
static size_t filter_differences_ssse3(const uint8_t *row, const uint8_t *above,
                                       size_t size, uint8_t *sub, uint8_t *up)
{
    size_t i = 0;
    size_t sub_score = 0;
    size_t up_score = 0;
    for (; i < 4; i++) {
        sub[i] = row[i];
        up[i] = (uint8_t)(row[i] - above[i]);
        sub_score += magnitude(sub[i]);
        up_score += magnitude(up[i]);
    }
    __m128i sub_sums = _mm_setzero_si128();
    __m128i up_sums = _mm_setzero_si128();
    const __m128i zero = _mm_setzero_si128();
    for (; size - i >= 16; i += 16) {
        const __m128i current = _mm_loadu_si128((const __m128i *)(row + i));
        const __m128i left = _mm_loadu_si128((const __m128i *)(row + i - 4));
        const __m128i previous = _mm_loadu_si128((const __m128i *)(above + i));
        const __m128i sub_bytes = _mm_sub_epi8(current, left);
        const __m128i up_bytes = _mm_sub_epi8(current, previous);
        _mm_storeu_si128((__m128i *)(sub + i), sub_bytes);
        _mm_storeu_si128((__m128i *)(up + i), up_bytes);
        sub_sums = _mm_add_epi64(sub_sums, _mm_sad_epu8(_mm_abs_epi8(sub_bytes), zero));
        up_sums = _mm_add_epi64(up_sums, _mm_sad_epu8(_mm_abs_epi8(up_bytes), zero));
    }
    uint64_t scores[2];
    _mm_storeu_si128((__m128i *)scores, sub_sums);
    sub_score += scores[0] + scores[1];
    _mm_storeu_si128((__m128i *)scores, up_sums);
    up_score += scores[0] + scores[1];
    for (; i < size; i++) {
        sub[i] = (uint8_t)(row[i] - row[i - 4]);
        up[i] = (uint8_t)(row[i] - above[i]);
        sub_score += magnitude(sub[i]);
        up_score += magnitude(up[i]);
    }
    return up_score < sub_score;
}
#endif

void leo_png_filter_rgba(const uint8_t *rgba, size_t row_bytes, size_t height,
                         uint8_t *filtered, uint8_t *up, int allow_simd)
{
    size_t (*choose_up)(const uint8_t *, const uint8_t *, size_t, uint8_t *, uint8_t *) =
        filter_differences;
#if HAVE_SSSE3
    if (allow_simd && __builtin_cpu_supports("ssse3"))
        choose_up = filter_differences_ssse3;
#else
    (void)allow_simd;
#endif

    // PNG Sub predicts the first pixel from zeros. Above is absent on row zero.
    filtered[0] = 1;
    memcpy(filtered + 1, rgba, 4);
    for (size_t i = 4; i < row_bytes; i++)
        filtered[1 + i] = (uint8_t)(rgba[i] - rgba[i - 4]);

    for (size_t y = 1; y < height; y++) {
        rgba += row_bytes;
        filtered += row_bytes + 1;
        const uint8_t *above = rgba - row_bytes;
        if (memcmp(rgba, above, row_bytes) == 0) {
            filtered[0] = 2;
            memset(filtered + 1, 0, row_bytes);
        } else if (choose_up(rgba, above, row_bytes, filtered + 1, up)) {
            filtered[0] = 2;
            memcpy(filtered + 1, up, row_bytes);
        } else {
            filtered[0] = 1;
        }
    }
}
