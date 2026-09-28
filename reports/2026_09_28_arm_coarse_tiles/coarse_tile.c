#include "coarse_tile.h"
#include <math.h>

#if defined(__ARM_NEON)
#include <arm_neon.h>

static float32x4_t tile_magnitude(float32x4_t real,float32x4_t imag)
{
    float32x4_t squared=vaddq_f32(vmulq_f32(real,real),vmulq_f32(imag,imag));
    float32x4_t safe=vbslq_f32(vceqq_f32(squared,vdupq_n_f32(0)),
        vdupq_n_f32(1),squared);
    float32x4_t reciprocal=vrsqrteq_f32(safe);
    reciprocal=vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe,reciprocal),reciprocal));
    reciprocal=vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe,reciprocal),reciprocal));
    return vmulq_f32(squared,reciprocal);
}

#define ACCUMULATE_CFO(lane) do { \
    float coefficient_real=vgetq_lane_f32(coeff_real,lane); \
    float coefficient_imag=vgetq_lane_f32(coeff_imag,lane); \
    r##lane=vaddq_f32(r##lane,vaddq_f32(vmulq_n_f32(x.val[0],coefficient_real), \
        vmulq_n_f32(x.val[1],coefficient_imag))); \
    i##lane=vaddq_f32(i##lane,vsubq_f32(vmulq_n_f32(x.val[1],coefficient_real), \
        vmulq_n_f32(x.val[0],coefficient_imag))); \
} while (0)

#define SCATTER_CFO(lane) do { \
    float32x4_t value=vmulq_f32(tile_magnitude(r##lane,i##lane),inverse); \
    sum[cfo+lane]+=vgetq_lane_f32(value,0); \
    sum[12+cfo+lane]+=vgetq_lane_f32(value,1); \
    sum[24+cfo+lane]+=vgetq_lane_f32(value,2); \
    sum[36+cfo+lane]+=vgetq_lane_f32(value,3); \
} while (0)

void leo_coarse_tile4_add(const float *samples,const float *real,
    const float *imag,int taps,const float inverse_norm[4],float *sum)
{
    float32x4_t inverse=vld1q_f32(inverse_norm);
#if defined(LEO_COARSE_TILE_CFO2)
    for (int cfo=0;cfo<12;cfo+=2) {
        float32x4_t r0=vdupq_n_f32(0),r1=r0,i0=r0,i1=r0;
        for (int k=0;k<taps;++k) {
            float32x4x2_t x=vld2q_f32(samples+2*k);
            float32x4_t coeff_real=vld1q_f32(real+12*k+cfo);
            float32x4_t coeff_imag=vld1q_f32(imag+12*k+cfo);
            ACCUMULATE_CFO(0);ACCUMULATE_CFO(1);
        }
        SCATTER_CFO(0);SCATTER_CFO(1);
    }
#else
    for (int cfo=0;cfo<12;cfo+=4) {
        float32x4_t r0=vdupq_n_f32(0),r1=r0,r2=r0,r3=r0;
        float32x4_t i0=r0,i1=r0,i2=r0,i3=r0;
        for (int k=0;k<taps;++k) {
            float32x4x2_t x=vld2q_f32(samples+2*k);
            float32x4_t coeff_real=vld1q_f32(real+12*k+cfo);
            float32x4_t coeff_imag=vld1q_f32(imag+12*k+cfo);
            ACCUMULATE_CFO(0);ACCUMULATE_CFO(1);
            ACCUMULATE_CFO(2);ACCUMULATE_CFO(3);
        }
        SCATTER_CFO(0);SCATTER_CFO(1);SCATTER_CFO(2);SCATTER_CFO(3);
    }
#endif
}

#undef ACCUMULATE_CFO
#undef SCATTER_CFO
#else
void leo_coarse_tile4_add(const float *samples,const float *real,
    const float *imag,int taps,const float inverse_norm[4],float *sum)
{
    for (int cfo=0;cfo<12;++cfo) {
        float r[4]={0},i[4]={0};
        for (int k=0;k<taps;++k) for (int epoch=0;epoch<4;++epoch) {
            float xr=samples[2*(k+epoch)],xi=samples[2*(k+epoch)+1];
            r[epoch]+=xr*real[12*k+cfo]+xi*imag[12*k+cfo];
            i[epoch]+=xi*real[12*k+cfo]-xr*imag[12*k+cfo];
        }
        for (int epoch=0;epoch<4;++epoch)
            sum[12*epoch+cfo]+=sqrtf(r[epoch]*r[epoch]+i[epoch]*i[epoch])*
                inverse_norm[epoch];
    }
}
#endif
