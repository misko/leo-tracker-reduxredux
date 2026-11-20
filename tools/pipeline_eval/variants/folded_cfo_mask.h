#ifndef LEO_FOLDED_CFO_MASK_H
#define LEO_FOLDED_CFO_MASK_H

/* Included after the frozen float coarse kernel's magnitude implementation. */
static unsigned folded_cfo_mask(const leo_presence_workspace *w, double folded)
{
    unsigned mask=0;
    const double period=10000000.0/44.0;
    for(int f=0; f<WIDE_REGIONAL_BINS; ++f)
        if(fabs(remainder(w->frequencies[f]-folded,period))<=80000.0)
            mask|=1u<<f;
    return mask;
}

static unsigned folded_epoch_mask(const leo_presence_workspace *w, ptrdiff_t epoch)
{
    ptrdiff_t i=epoch-w->folded_epoch+1;
    return i>=0 && i<3 ? w->folded_masks[i] : 0;
}

static unsigned folded_cfo_count(unsigned mask)
{
    unsigned count=0;
    for(;mask;mask&=mask-1) ++count;
    return count;
}

static void folded_cfo_float_add(const float *samples, const float *real,
    const float *imag, int taps, float inverse, float *sum, unsigned mask)
{
    for(int f=0; f<WIDE_REGIONAL_BINS; ++f) {
        if(!(mask & (1u<<f))) continue;
        float r=0, i=0;
        for(int k=0; k<taps; ++k) {
            float rr=real[CFO_COUNT*k+f], ri=imag[CFO_COUNT*k+f];
            r+=samples[2*k]*rr+samples[2*k+1]*ri;
            i+=samples[2*k+1]*rr-samples[2*k]*ri;
        }
#if defined(__ARM_NEON)
        sum[f]+=vgetq_lane_f32(coarse_magnitude(vdupq_n_f32(r),vdupq_n_f32(i)),0)*inverse;
#else
        sum[f]+=sqrtf(r*r+i*i)*inverse;
#endif
    }
}

#endif
