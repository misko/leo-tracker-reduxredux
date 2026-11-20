/* Internal exact retained-band layout for the ordinary fine acquisition. */
#ifndef LEO_ORDINARY_GLRT_FINE_H
#define LEO_ORDINARY_GLRT_FINE_H

static inline size_t leo_fine_band_radius(size_t size, double step_hz)
{
    const size_t radius=(size_t)ceil(400000.0/step_hz);
    return radius < (size-1)/2 ? radius : (size-1)/2;
}

static inline size_t leo_fine_band_index(size_t bin, size_t size, size_t radius)
{
    return bin <= radius ? radius+bin : bin-(size-radius);
}

static inline void leo_fine_band_copy(float complex *dst, const float complex *src,
    size_t size, size_t radius)
{
    memcpy(dst,src+size-radius,radius*sizeof(*dst));
    memcpy(dst+radius,src,(radius+1)*sizeof(*dst));
}

/* CI16 squares sum exactly in both representations at supported dwell sizes.
 * The normalized prefix represents every term in units of 2^-30. */
static inline double leo_fine_span_energy(const double *prefix, int start, int stop)
{
    return (prefix[stop]-prefix[start])*0x1p30;
}

#endif
