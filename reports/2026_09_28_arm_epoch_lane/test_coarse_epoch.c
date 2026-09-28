#include "coarse_epoch.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

static uint32_t state=UINT32_C(0x91e10da5);
static float value(void)
{
    state=state*UINT32_C(1664525)+UINT32_C(1013904223);
    return ((int32_t)(state>>12)-524288)*0x1p-19f;
}

#if defined(__ARM_NEON)
static float32x4_t reference_magnitude(float32x4_t real,float32x4_t imag)
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

static void reference_add(const float *samples,const float *real,
    const float *imag,int taps,float inverse,float *sum)
{
    float32x4_t r0=vdupq_n_f32(0),r1=r0,r2=r0,i0=r0,i1=r0,i2=r0;
    for (int k=0;k<taps;++k) {
        float32x4_t xr=vdupq_n_f32(samples[2*k]),xi=vdupq_n_f32(samples[2*k+1]);
#define LANE(lane) do { \
    float32x4_t rr=vld1q_f32(real+12*k+4*lane); \
    float32x4_t ri=vld1q_f32(imag+12*k+4*lane); \
    r##lane=vaddq_f32(r##lane,vaddq_f32(vmulq_f32(xr,rr),vmulq_f32(xi,ri))); \
    i##lane=vaddq_f32(i##lane,vsubq_f32(vmulq_f32(xi,rr),vmulq_f32(xr,ri))); \
} while (0)
        LANE(0);LANE(1);LANE(2);
#undef LANE
    }
#define STORE(lane) vst1q_f32(sum+4*lane,vaddq_f32(vld1q_f32(sum+4*lane), \
    vmulq_n_f32(reference_magnitude(r##lane,i##lane),inverse)))
    STORE(0);STORE(1);STORE(2);
#undef STORE
}
#else
static void reference_add(const float *samples,const float *real,
    const float *imag,int taps,float inverse,float *sum)
{
    float r[12]={0},i[12]={0};
    for (int k=0;k<taps;++k) for (int f=0;f<12;++f) {
        r[f]+=samples[2*k]*real[12*k+f]+samples[2*k+1]*imag[12*k+f];
        i[f]+=samples[2*k+1]*real[12*k+f]-samples[2*k]*imag[12*k+f];
    }
    for (int f=0;f<12;++f) sum[f]+=sqrtf(r[f]*r[f]+i[f]*i[f])*inverse;
}
#endif

static void one(int taps,int zero_energy)
{
    float samples[2*(45+3)],real[45*12],imag[45*12];
    float expected[48],actual[48],inverse[4];
    for (size_t k=0;k<sizeof(samples)/sizeof(*samples);++k) samples[k]=value();
    for (size_t k=0;k<sizeof(real)/sizeof(*real);++k) {real[k]=value();imag[k]=value();}
    for (int k=0;k<48;++k) expected[k]=actual[k]=value();
    for (int epoch=0;epoch<4;++epoch) {
        inverse[epoch]=zero_energy ? 0 : fabsf(value())+.125f;
        reference_add(samples+2*epoch,real,imag,taps,inverse[epoch],expected+12*epoch);
    }
    leo_coarse_epoch4_add(samples,real,imag,taps,inverse,actual);
    assert(!memcmp(expected,actual,sizeof(expected)));
}

int main(void)
{
    const int taps[]={1,2,3,4,11,17,22,33,44,45};
    for (size_t k=0;k<sizeof(taps)/sizeof(*taps);++k) {
        one(taps[k],0);one(taps[k],1);
    }
    puts("coarse epoch-lane exact-parity tests passed");
    return 0;
}
