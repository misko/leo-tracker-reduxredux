/* Experimental per-visit little-endian signed block floating point. */
#include <stddef.h>
#include <stdint.h>

static int quantize(int value, unsigned shift, int rail, size_t *clips) {
    int magnitude = value < 0 ? -value : value;
    int bias = shift ? 1 << (shift - 1) : 0;
    int nearest = (magnitude + bias) >> shift;
    int q = value < 0 ? -nearest : nearest;
    if (q >= rail) {
        ++*clips;
        return rail - 1;
    }
    return q;
}

static int restore(unsigned q, int rail, unsigned shift) {
    int signed_word = (int)(q ^ (unsigned)rail) - rail;
    return signed_word * (1 << shift);
}

static int valid_size(size_t words, size_t bytes, unsigned width) {
    return words && words % 4 == 0 && words <= (SIZE_MAX - 1) / 2 &&
           (width == 8 || width == 10) && bytes == 1 + words / 4 * (width / 2);
}

int encode_visit(const int16_t *samples, size_t words, unsigned width,
                 uint8_t *encoded, size_t bytes, size_t *clips) {
    if (!valid_size(words, bytes, width)) return -1;
    int low = 0, high = 0;
    for (size_t i = 0; i < words; ++i) {
        int value = samples[i];
        if (value < low) low = value;
        if (value > high) high = value;
    }
    unsigned shift = 0;
    int rail = 1 << (width - 1);
    while (low < -(rail << shift) || high >= rail << shift) ++shift;
    encoded[0] = (uint8_t)shift;
    *clips = 0;
    if (width == 8) {
        for (size_t i = 0; i < words; ++i)
            encoded[i + 1] = (uint8_t)quantize(samples[i], shift, rail, clips);
    } else {
        for (size_t i = 0, at = 1; i < words; i += 4, at += 5) {
            uint64_t block = 0;
            for (unsigned j = 0; j < 4; ++j)
                block |= (uint64_t)(quantize(samples[i + j], shift, rail, clips) & 1023) << (10 * j);
            for (unsigned j = 0; j < 5; ++j) encoded[at + j] = (uint8_t)(block >> (8 * j));
        }
    }
    return 0;
}

int decode_visit(const uint8_t *encoded, size_t bytes, unsigned width,
                 int16_t *samples, size_t words) {
    if (!valid_size(words, bytes, width) || encoded[0] > 16 - width) return -1;
    unsigned shift = encoded[0];
    int rail = 1 << (width - 1);
    if (width == 8) {
        for (size_t i = 0; i < words; ++i)
            samples[i] = (int16_t)restore(encoded[1 + i], rail, shift);
    } else {
        for (size_t i = 0, at = 1; i < words; i += 4, at += 5) {
            uint64_t block = 0;
            for (unsigned j = 0; j < 5; ++j) block |= (uint64_t)encoded[at + j] << (8 * j);
            for (unsigned j = 0; j < 4; ++j)
                samples[i + j] = (int16_t)restore((unsigned)(block >> (10 * j)) & 1023, rail, shift);
        }
    }
    return 0;
}
