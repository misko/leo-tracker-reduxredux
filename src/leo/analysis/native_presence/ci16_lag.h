/* Exact integer lag products for bounded CI16 probes (at most 100000 complex
 * samples). Each component sum is below 2^48, hence exactly representable in
 * both int64_t and FP64. Widen BEFORE summing products: two INT16_MIN squares
 * would overflow a signed 32-bit lane. No precision reduction is involved. */
#include <complex.h>
#include <stddef.h>
#include <stdint.h>
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
#include <arm_neon.h>
#endif

static double complex ci16_lag_sum(const int16_t *iq, size_t count, size_t lag)
{
    size_t k=0, end=count-lag;
    int64_t real=0, imag=0;
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
    int64x2_t re=vdupq_n_s64(0), im=vdupq_n_s64(0);
    for (; k+3<end; k+=4) {
        int16x4x2_t a=vld2_s16(iq+2*k), b=vld2_s16(iq+2*(k+lag));
        re=vpadalq_s32(re,vmull_s16(a.val[0],b.val[0]));
        re=vpadalq_s32(re,vmull_s16(a.val[1],b.val[1]));
        im=vpadalq_s32(im,vmull_s16(a.val[0],b.val[1]));
        im=vsubq_s64(im,vpaddlq_s32(vmull_s16(a.val[1],b.val[0])));
    }
    int64_t re_lanes[2], im_lanes[2];
    vst1q_s64(re_lanes,re); vst1q_s64(im_lanes,im);
    real=re_lanes[0]+re_lanes[1]; imag=im_lanes[0]+im_lanes[1];
#endif
    for (; k<end; ++k) {
        int64_t ar=iq[2*k], ai=iq[2*k+1], br=iq[2*(k+lag)], bi=iq[2*(k+lag)+1];
        real+=ar*br+ai*bi; imag+=ar*bi-ai*br;
    }
    return (double)real+I*(double)imag;
}
