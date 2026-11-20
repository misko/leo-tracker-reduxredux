/* Included by the isolated wave8 release overlay after its stock FP32 kernel.
 * A four-lane ARM group retains the original per-bin tap order and magnitude.
 * The padded tail is private and never contributes a coarse peak. */
#ifndef LEO_WIDE_REGIONAL_CFO_H
#define LEO_WIDE_REGIONAL_CFO_H

static void wide_regional_float_add(const float *samples, const float *real,
    const float *imag, int taps, float inverse, float *sum)
{
#if defined(__ARM_NEON)
    for (int f=0;f<CFO_COUNT;f+=4) {
        float32x4_t r=vdupq_n_f32(0.0f), i=r;
        for (int k=0;k<taps;++k) {
            float32x4_t xr=vdupq_n_f32(samples[2*k]);
            float32x4_t xi=vdupq_n_f32(samples[2*k+1]);
            float32x4_t rr=vld1q_f32(real+CFO_COUNT*k+f);
            float32x4_t ri=vld1q_f32(imag+CFO_COUNT*k+f);
            r=vaddq_f32(r,vaddq_f32(vmulq_f32(xr,rr),vmulq_f32(xi,ri)));
            i=vaddq_f32(i,vsubq_f32(vmulq_f32(xi,rr),vmulq_f32(xr,ri)));
        }
        vst1q_f32(sum+f,vaddq_f32(vld1q_f32(sum+f),
            vmulq_n_f32(coarse_magnitude(r,i),inverse)));
    }
#else
    float r[CFO_COUNT]={0}, i[CFO_COUNT]={0};
    for (int k=0;k<taps;++k)
        for (int f=0;f<CFO_COUNT;++f) {
            r[f]+=samples[2*k]*real[CFO_COUNT*k+f]+samples[2*k+1]*imag[CFO_COUNT*k+f];
            i[f]+=samples[2*k+1]*real[CFO_COUNT*k+f]-samples[2*k]*imag[CFO_COUNT*k+f];
        }
    for (int f=0;f<WIDE_REGIONAL_BINS;++f) sum[f]+=sqrtf(r[f]*r[f]+i[f]*i[f])*inverse;
#endif
}

#endif
