#ifndef LEO_CI16_ENERGY_PREFIX_H
#define LEO_CI16_ENERGY_PREFIX_H
#include <stddef.h>

/* A CI16 complex sample has integer squared energy <= 2^31. Through
 * 2^22 source samples the unnormalized prefix is <= 2^53, so both the
 * original sums and the normalized prefix differences are exact binary64.
 * The owner must attest the ENTIRE source prefix length, not just a slice.
 * Arbitrary floating samples and longer source histories must use direct sums. */
#define LEO_CI16_EXACT_PREFIX_MAX_SAMPLES ((size_t)1 << 22)

static inline double leo_ci16_window_energy(const double *normalized_prefix,
    size_t begin,size_t count)
{
    return (normalized_prefix[begin+count]-normalized_prefix[begin])*0x1p30;
}
#endif
