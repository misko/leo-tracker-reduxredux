#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(__SSE2__)
#include <emmintrin.h>
#endif

static void sub(uint8_t *out, const uint8_t *row, size_t width)
{
    size_t offset = 0;
#if defined(__SSE2__)
    __m128i carry = _mm_setzero_si128();
    for (; width - offset >= 16; offset += 16) {
        __m128i pixels = _mm_loadu_si128((const __m128i *)(row + offset));
        pixels = _mm_add_epi8(pixels, _mm_slli_si128(pixels, 4));
        pixels = _mm_add_epi8(pixels, _mm_slli_si128(pixels, 8));
        pixels = _mm_add_epi8(pixels, carry);
        _mm_storeu_si128((__m128i *)(out + offset), pixels);
        carry = _mm_shuffle_epi32(pixels, _MM_SHUFFLE(3, 3, 3, 3));
    }
#endif
    for (; offset < width; ++offset)
        out[offset] = row[offset] + (offset < 4 ? 0 : out[offset - 4]);
}

static void up(uint8_t *out, const uint8_t *row, const uint8_t *previous, size_t width)
{
    size_t offset = 0;
#if defined(__SSE2__)
    for (; width - offset >= 16; offset += 16) {
        __m128i pixels = _mm_loadu_si128((const __m128i *)(row + offset));
        __m128i top = _mm_loadu_si128((const __m128i *)(previous + offset));
        _mm_storeu_si128((__m128i *)(out + offset), _mm_add_epi8(pixels, top));
    }
#endif
    for (; offset < width; ++offset)
        out[offset] = row[offset] + previous[offset];
}

/* The input is exactly height * (4 * width + 1) inflated scanline bytes.
 * Compact forward in the same buffer. A row's source always starts to the
 * right of its destination, and the previous destination is already packed. */
int leo_verified_rgba_rows(uint8_t *buffer, size_t length, size_t width, size_t height)
{
    if (!width || !height || width > (SIZE_MAX - 1) / 4)
        return 0;
    const size_t stride = width * 4;
    if (height > length / (stride + 1) || height * (stride + 1) != length)
        return 0;
    for (size_t i = 0; i < height; ++i) {
        uint8_t *out = buffer + i * stride;
        const uint8_t *encoded = buffer + i * (stride + 1);
        const uint8_t *row = encoded + 1;
        switch (*encoded) {
        case 0:
            memmove(out, row, stride);
            break;
        case 1:
            sub(out, row, stride);
            break;
        case 2:
            if (i == 0)
                memmove(out, row, stride);
            else
                up(out, row, out - stride, stride);
            break;
        default:
            return 0;
        }
    }
    return 1;
}
