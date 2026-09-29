#ifndef OPT_CI16_ENERGY_V2
#define OPT_CI16_ENERGY_V2
#include <stdint.h>
#include <stddef.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
/* Up to 200000 CI16 samples: sum <=200000*2^31<2^49. This exactly matches
 * the original sequential FP64 energy sum, including signed-CI16 extrema. */
static double opt_ci16_energy(const int16_t *iq,size_t count)
{
    size_t k=0;int64_t total=0;
#if defined(__ARM_NEON)
    int64x2_t lo=vdupq_n_s64(0),hi=lo;
    for(;k+3<count;k+=4){
        int16x4x2_t a=vld2_s16(iq+2*k);
        int32x4_t r=vmull_s16(a.val[0],a.val[0]),i=vmull_s16(a.val[1],a.val[1]);
        lo=vaddq_s64(lo,vaddl_s32(vget_low_s32(r),vget_low_s32(i)));
        hi=vaddq_s64(hi,vaddl_s32(vget_high_s32(r),vget_high_s32(i)));
    }
    int64_t lanes[2];vst1q_s64(lanes,vaddq_s64(lo,hi));total=lanes[0]+lanes[1];
#endif
    for(;k<count;++k){int64_t r=iq[2*k],i=iq[2*k+1];total+=r*r+i*i;}
    return (double)total;
}
#endif
