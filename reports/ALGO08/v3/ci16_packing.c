/* Private lossless signed little-endian CI16 block codec. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(__SSSE3__)
#include <tmmintrin.h>
#endif

void ci16_occupied_bits(const int16_t *samples, size_t words, unsigned *width, unsigned *shift) {
    int16_t low = 0, high = 0;
    uint16_t used = 0;
    for (size_t i = 0; i < words; ++i) {
        int16_t value = samples[i];
        if (value < low) low = value;
        if (value > high) high = value;
        used |= (uint16_t)value;
    }
    unsigned zeros = 0;
    if (used) {
        while (!(used & 1u)) {
            ++zeros;
            used >>= 1;
        }
    }
    int scale = 1 << zeros;
    int minimum = low / scale, maximum = high / scale;
    unsigned bits = 1;
    int half = 1;
    while (minimum < -half || maximum >= half) {
        half *= 2;
        ++bits;
    }
    *width = bits;
    *shift = zeros;
}

static size_t packed_bytes(size_t words, unsigned width, unsigned shift) {
    if (!words || width < 1 || width > 16 || shift > 15 || width + shift > 16 ||
        words > (SIZE_MAX - 7) / 16) return 0;
    return (words * width + 7) / 8;
}

int ci16_pack(const int16_t *samples, size_t words, unsigned width, unsigned shift,
              uint8_t *out, size_t bytes) {
    if (!bytes || bytes != packed_bytes(words, width, shift)) return -1;
    if (width == 16) {
        memcpy(out, samples, bytes);
        return 0;
    }
    size_t i = 0, written = 0;
#if defined(__SSSE3__)
    if (width == 12) {
        __m128i pairs = _mm_setr_epi16(1, 4096, 1, 4096, 1, 4096, 1, 4096);
        __m128i order = _mm_setr_epi8(0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, -1, -1, -1, -1);
        __m128i cut = _mm_set1_epi16(4095);
        __m128i displacement = _mm_cvtsi32_si128((int)shift);
        for (; words - i >= 8; i += 8, written += 12) {
            __m128i values = _mm_loadu_si128((const __m128i *)(samples + i));
            values = _mm_and_si128(_mm_srl_epi16(values, displacement), cut);
            __m128i dense = _mm_shuffle_epi8(_mm_madd_epi16(values, pairs), order);
            _mm_storel_epi64((__m128i *)(out + written), dense);
            uint32_t tail = (uint32_t)_mm_cvtsi128_si32(_mm_srli_si128(dense, 8));
            memcpy(out + written + 8, &tail, sizeof(tail));
        }
    }
#endif
    uint32_t pending = 0, mask = (1u << width) - 1u;
    unsigned held = 0;
    for (; i < words; ++i) {
        uint32_t value = ((uint16_t)samples[i] >> shift) & mask;
        pending |= value << held;
        held += width;
        while (held >= 8) {
            out[written++] = (uint8_t)pending;
            pending >>= 8;
            held -= 8;
        }
    }
    if (held) out[written++] = (uint8_t)pending;
    return written == bytes ? 0 : -1;
}

int ci16_unpack(const uint8_t *data, size_t bytes, unsigned width, unsigned shift,
                int16_t *samples, size_t words) {
    if (!bytes || bytes != packed_bytes(words, width, shift)) return -1;
    if (width == 16) {
        memcpy(samples, data, bytes);
        return 0;
    }
    unsigned used = (unsigned)((words * width) % 8);
    if (used && data[bytes - 1] >> used) return -1;
    size_t i = 0, consumed = 0;
#if defined(__SSSE3__)
    if (width == 12) {
        __m128i order = _mm_setr_epi8(0, 1, 2, -1, 3, 4, 5, -1, 6, 7, 8, -1, 9, 10, 11, -1);
        __m128i first = _mm_set1_epi32(0x00000fff);
        __m128i second = _mm_set1_epi32(0x0fff0000);
        __m128i displacement = _mm_cvtsi32_si128((int)shift);
        for (; words - i >= 8; i += 8, consumed += 12) {
            __m128i front = _mm_loadl_epi64((const __m128i *)(data + consumed));
            uint32_t tail;
            memcpy(&tail, data + consumed + 8, sizeof(tail));
            __m128i dense = _mm_or_si128(front, _mm_slli_si128(_mm_cvtsi32_si128((int)tail), 8));
            __m128i pairs = _mm_shuffle_epi8(dense, order);
            __m128i values = _mm_or_si128(_mm_and_si128(pairs, first),
                                          _mm_and_si128(_mm_slli_epi32(pairs, 4), second));
            values = _mm_srai_epi16(_mm_slli_epi16(values, 4), 4);
            _mm_storeu_si128((__m128i *)(samples + i), _mm_sll_epi16(values, displacement));
        }
    }
#endif
    uint32_t pending = 0, mask = (1u << width) - 1u, sign = 1u << (width - 1);
    unsigned held = 0;
    int scale = 1 << shift;
    for (; i < words; ++i) {
        while (held < width) {
            pending |= (uint32_t)data[consumed++] << held;
            held += 8;
        }
        uint32_t value = pending & mask;
        samples[i] = (int16_t)(((int)(value ^ sign) - (int)sign) * scale);
        pending >>= width;
        held -= width;
    }
    return consumed == bytes ? 0 : -1;
}
