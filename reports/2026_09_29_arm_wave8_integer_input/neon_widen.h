#if defined(__ARM_NEON)
#include <arm_neon.h>
/* Exact widening for zero or a normal binary32 value. Here inputs originate
 * from CI16, so infinities, NaNs and subnormals are impossible. */
static uint64x2_t widen_normal_float_bits(uint32x2_t bits)
{
    uint32x2_t magnitude=vand_u32(bits,vdup_n_u32(0x7fffffff));
    uint64x2_t payload=vaddq_u64(vshll_n_u32(magnitude,29),vdupq_n_u64(UINT64_C(896)<<52));
    uint64x2_t zero=vmovl_u32(vceq_u32(magnitude,vdup_n_u32(0)));
    zero=vorrq_u64(zero,vshlq_n_u64(zero,32));
    payload=vbicq_u64(payload,zero);
    uint64x2_t sign=vshlq_n_u64(vmovl_u32(vand_u32(bits,vdup_n_u32(0x80000000))),32);
    return vorrq_u64(payload,sign);
}
static void store_raw_four(double complex *dst,float32x4_t re,float32x4_t im)
{
    uint32x4_t r=vreinterpretq_u32_f32(re),i=vreinterpretq_u32_f32(im);
    uint64x2x2_t a={{widen_normal_float_bits(vget_low_u32(r)),widen_normal_float_bits(vget_low_u32(i))}};
    uint64x2x2_t b={{widen_normal_float_bits(vget_high_u32(r)),widen_normal_float_bits(vget_high_u32(i))}};
    /* Local bit arrays plus memcpy avoid writing double objects through an
     * incompatible uint64_t pointer under strict aliasing. */
    uint64_t words[8];
    vst1q_u64(words,vcombine_u64(vget_low_u64(a.val[0]),vget_low_u64(a.val[1])));
    vst1q_u64(words+2,vcombine_u64(vget_high_u64(a.val[0]),vget_high_u64(a.val[1])));
    vst1q_u64(words+4,vcombine_u64(vget_low_u64(b.val[0]),vget_low_u64(b.val[1])));
    vst1q_u64(words+6,vcombine_u64(vget_high_u64(b.val[0]),vget_high_u64(b.val[1])));
    memcpy(dst,words,sizeof(words));
}
static size_t prepare_neon_prefix(leo_dwell_input *d,const int16_t *iq,size_t count,int rx,double *sum)
{
    size_t k=0;
    for(;k+4<=count;k+=4){
        int16x4x4_t input=vld4_s16(iq+4*k);
        int16x4_t ir=input.val[2*rx],ii=input.val[2*rx+1];
        float32x4_t re=vcvtq_f32_s32(vmovl_s16(ir)),im=vcvtq_f32_s32(vmovl_s16(ii));
        store_raw_four(d->raw[rx]+k,re,im);
        float32x4x2_t normalized={{vmulq_n_f32(re,1.0f/32768.0f),vmulq_n_f32(im,1.0f/32768.0f)}};
        vst2q_f32(d->normalized[rx]+2*k,normalized);
        uint32x4_t energy=vaddq_u32(vreinterpretq_u32_s32(vmull_s16(ir,ir)),vreinterpretq_u32_s32(vmull_s16(ii,ii)));
        uint32_t words[4];vst1q_u32(words,energy);
        for(int j=0;j<4;++j){*sum+=(double)words[j]*(1.0/1073741824.0);d->prefix[rx][k+j+1]=*sum;}
    }
    return k;
}
#endif
