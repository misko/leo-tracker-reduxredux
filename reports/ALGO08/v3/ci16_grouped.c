/* Exact v1 CI16 wire codec with grouped fixed-width scalar words. */
#define ci16_pack ci16_original_pack
#define ci16_unpack ci16_original_unpack
#include "ci16_packing.c"
#undef ci16_pack
#undef ci16_unpack

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define CI16_GROUPED 1

static inline uint64_t low_bytes(const uint8_t *data, size_t bytes) {
    uint64_t value = 0;
    memcpy(&value, data, bytes);
    return value;
}

static inline uint64_t field(int16_t sample, unsigned shift, uint64_t mask) {
    return ((uint16_t)sample >> shift) & mask;
}

static inline int16_t signed_field(uint64_t value, uint64_t mask, int sign, int scale) {
    return (int16_t)(((int)((value & mask) ^ (uint64_t)sign) - sign) * scale);
}

/* Eight words always occupy exactly B bytes. Each four-word register needs
 * at most 60 bits. Odd widths share the middle byte at its nibble boundary. */
#define WIDTH(B) \
static size_t pack_##B(const int16_t *src, size_t words, unsigned shift, uint8_t *dst) { \
    const uint64_t mask = (UINT64_C(1) << (B)) - 1; \
    const unsigned low = (B) / 2, high = (B) - low, bridge = ((B) % 2) * 4; \
    size_t i = 0; \
    for (; words - i >= 8; i += 8, dst += (B)) { \
        uint64_t left = field(src[i], shift, mask) | (field(src[i + 1], shift, mask) << (B)) \
            | (field(src[i + 2], shift, mask) << (2 * (B))) | (field(src[i + 3], shift, mask) << (3 * (B))); \
        uint64_t right = field(src[i + 4], shift, mask) | (field(src[i + 5], shift, mask) << (B)) \
            | (field(src[i + 6], shift, mask) << (2 * (B))) | (field(src[i + 7], shift, mask) << (3 * (B))); \
        right = (right << bridge) | (left >> (8 * low)); \
        memcpy(dst, &left, low); \
        memcpy(dst + low, &right, high); \
    } \
    return i; \
} \
static size_t unpack_##B(const uint8_t *src, size_t words, unsigned shift, int16_t *dst) { \
    const uint64_t mask = (UINT64_C(1) << (B)) - 1; \
    const unsigned low = (B) / 2, high = (B) - low, bridge = ((B) % 2) * 4; \
    const int sign = 1 << ((B) - 1), scale = 1 << shift; \
    size_t i = 0; \
    for (; words - i >= 8; i += 8, src += (B)) { \
        const uint64_t middle = low_bytes(src + low, high); \
        const uint64_t left = low_bytes(src, low) | (middle << (8 * low)); \
        const uint64_t right = middle >> bridge; \
        dst[i] = signed_field(left, mask, sign, scale); \
        dst[i + 1] = signed_field(left >> (B), mask, sign, scale); \
        dst[i + 2] = signed_field(left >> (2 * (B)), mask, sign, scale); \
        dst[i + 3] = signed_field(left >> (3 * (B)), mask, sign, scale); \
        dst[i + 4] = signed_field(right, mask, sign, scale); \
        dst[i + 5] = signed_field(right >> (B), mask, sign, scale); \
        dst[i + 6] = signed_field(right >> (2 * (B)), mask, sign, scale); \
        dst[i + 7] = signed_field(right >> (3 * (B)), mask, sign, scale); \
    } \
    return i; \
}

#define SCALAR_WIDTHS(OP) \
    OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9) OP(10) OP(11) OP(13) OP(14) OP(15)
SCALAR_WIDTHS(WIDTH)
#if !defined(__SSSE3__)
WIDTH(12)
#endif
#undef WIDTH
#endif

int ci16_pack(const int16_t *samples, size_t words, unsigned width, unsigned shift, uint8_t *out, size_t bytes) {
#if defined(CI16_GROUPED)
    if (!bytes || bytes != packed_bytes(words, width, shift)) return -1;
    size_t done = 0;
#define PACK(B) case B: done = pack_##B(samples, words, shift, out); break;
    switch (width) {
        SCALAR_WIDTHS(PACK)
#if !defined(__SSSE3__)
        PACK(12)
#endif
    }
#undef PACK
    if (done == words) return 0;
    const size_t saved = done / 8 * width;
    samples += done;
    words -= done;
    out += saved;
    bytes -= saved;
#endif
    return ci16_original_pack(samples, words, width, shift, out, bytes);
}

int ci16_unpack(const uint8_t *data, size_t bytes, unsigned width, unsigned shift, int16_t *samples, size_t words) {
#if defined(CI16_GROUPED)
    if (!bytes || bytes != packed_bytes(words, width, shift)) return -1;
    const unsigned padding_start = (unsigned)((words * width) % 8);
    if (padding_start && data[bytes - 1] >> padding_start) return -1;
    size_t done = 0;
#define UNPACK(B) case B: done = unpack_##B(data, words, shift, samples); break;
    switch (width) {
        SCALAR_WIDTHS(UNPACK)
#if !defined(__SSSE3__)
        UNPACK(12)
#endif
    }
#undef UNPACK
    if (done == words) return 0;
    const size_t saved = done / 8 * width;
    data += saved;
    bytes -= saved;
    samples += done;
    words -= done;
#endif
    return ci16_original_unpack(data, bytes, width, shift, samples, words);
}
