#include <stddef.h>
#include <stdint.h>

/* Raw offsets are the little-endian wire bytes of I0, Q0, I1 and Q1.
 * Keep the lows in sample order. The high planes have one byte per sample
 * and component, so their level patterns are contiguous for the codec. */
void ci16_separate(const uint8_t *restrict raw, uint8_t *restrict low,
                   uint8_t *restrict high, size_t samples)
{
    for (size_t i = 0; i < samples; ++i) {
        low[4*i] = raw[8*i];
        low[4*i + 1] = raw[8*i + 2];
        low[4*i + 2] = raw[8*i + 4];
        low[4*i + 3] = raw[8*i + 6];
        high[i] = raw[8*i + 1];
        high[samples + i] = raw[8*i + 3];
        high[2*samples + i] = raw[8*i + 5];
        high[3*samples + i] = raw[8*i + 7];
    }
}

void ci16_interleave(const uint8_t *restrict low, const uint8_t *restrict high,
                     uint8_t *restrict raw, size_t samples)
{
    for (size_t i = 0; i < samples; ++i) {
        raw[8*i] = low[4*i];
        raw[8*i + 1] = high[i];
        raw[8*i + 2] = low[4*i + 1];
        raw[8*i + 3] = high[samples + i];
        raw[8*i + 4] = low[4*i + 2];
        raw[8*i + 5] = high[2*samples + i];
        raw[8*i + 6] = low[4*i + 3];
        raw[8*i + 7] = high[3*samples + i];
    }
}
