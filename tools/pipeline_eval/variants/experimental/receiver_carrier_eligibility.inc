/* Included after the timing scout's FFT dimensions. */
#include <fenv.h>

typedef struct {
    int valid, rate, count;
    double lo, hi, center;
    uint16_t eligible[bins];
} CarrierEligibility;

static _Thread_local uint64_t eligibility_hits, eligibility_rebuilds;

void experimental_carrier_eligibility_stats(uint64_t out[2], int reset)
{
    out[0] = eligibility_hits;
    out[1] = eligibility_rebuilds;
    if (reset) eligibility_hits = eligibility_rebuilds = 0;
}

static double carrier_bin_at_rate(int index, int rate)
{
    return (index < bins / 2 ? index : index - bins) * (double)rate / bins;
}

int experimental_carrier_eligibility_update(CarrierEligibility *cache, int rate,
                                            double lo, double hi, double center)
{
    if (!cache || rate <= 0 || !(lo < hi) || !isfinite(lo) || !isfinite(hi) || !isfinite(center))
        return -1;
    int cacheable = fegetround() == FE_TONEAREST;
    if (cacheable && cache->valid && cache->rate == rate &&
        !memcmp(&lo, &cache->lo, sizeof(lo)) && !memcmp(&hi, &cache->hi, sizeof(hi)) &&
        !memcmp(&center, &cache->center, sizeof(center))) {
        ++eligibility_hits;
        return 0;
    }

    int used = 0;
    for (int index = 0; index < bins; ++index) {
        double f = carrier_bin_at_rate(index, rate) + center;
        if (ceil((lo - f) / rate) <= floor((hi - f) / rate))
            cache->eligible[used++] = (uint16_t)index;
    }
    cache->lo = lo;
    cache->hi = hi;
    cache->center = center;
    cache->rate = rate;
    cache->count = used;
    cache->valid = cacheable;
    ++eligibility_rebuilds;
    return 1;
}
