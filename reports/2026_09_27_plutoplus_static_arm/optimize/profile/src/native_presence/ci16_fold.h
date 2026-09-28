/* Exact folded power and lag products. At most sixteen terms per cell keep
 * every sum below 2^36; int64 and FP64 therefore represent the same sums.
 * Only unconditioned CI16 is eligible. Tone-subtracted/floating IQ must use
 * the original floating path. Scratch is fixed-size, never heap allocated. */
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
#include <arm_neon.h>
#endif

static void coarse_fold_ci16(leo_presence_workspace *w, const int16_t *iq, size_t count)
{
    for (size_t block=0; block<w->n; block+=256) {
        size_t width=w->n-block<256 ? w->n-block : 256;
        int64_t energy[256]={0}, real[256]={0}, imag[256]={0};
        int32_t support[256]={0}, diff_support[256]={0};
        for (int frame=0; frame<16; ++frame) {
            size_t start=(size_t)frame_start(w,0,frame);
            if (start>=count || count-start<=block) break;
            size_t valid=count-start-block;
            if (valid>width) valid=width;
            size_t available=count-start-block;
            size_t paired=available>LEO_PRESENCE_DIFFERENTIAL_LAG ?
                available-LEO_PRESENCE_DIFFERENTIAL_LAG : 0;
            if (paired>valid) paired=valid;
            size_t k=0;
#if defined(__ARM_NEON) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
            for (; k+3<paired; k+=4) {
                int16x4x2_t a=vld2_s16(iq+2*(start+block+k));
                int16x4x2_t b=vld2_s16(iq+2*(start+block+k+LEO_PRESENCE_DIFFERENTIAL_LAG));
                int32x4_t rr=vmull_s16(a.val[0],b.val[0]);
                int32x4_t ii=vmull_s16(a.val[1],b.val[1]);
                int32x4_t ri=vmull_s16(a.val[0],b.val[1]);
                int32x4_t ir=vmull_s16(a.val[1],b.val[0]);
                int32x4_t aa=vmull_s16(a.val[0],a.val[0]);
                int32x4_t bb=vmull_s16(a.val[1],a.val[1]);
                /* Widen EACH product before complex addition: CI16 extrema
                 * can overflow int32 even for a single power/lag sample. */
#define ADD_PAIR(dst, first, second, operation) do { \
    vst1q_s64(dst+k,vaddq_s64(vld1q_s64(dst+k),operation( \
        vmovl_s32(vget_low_s32(first)),vmovl_s32(vget_low_s32(second))))); \
    vst1q_s64(dst+k+2,vaddq_s64(vld1q_s64(dst+k+2),operation( \
        vmovl_s32(vget_high_s32(first)),vmovl_s32(vget_high_s32(second))))); \
} while (0)
                ADD_PAIR(real,rr,ii,vaddq_s64);
                ADD_PAIR(imag,ri,ir,vsubq_s64);
                ADD_PAIR(energy,aa,bb,vaddq_s64);
#undef ADD_PAIR
                vst1q_s32(support+k,vaddq_s32(vld1q_s32(support+k),vdupq_n_s32(1)));
                vst1q_s32(diff_support+k,vaddq_s32(vld1q_s32(diff_support+k),vdupq_n_s32(1)));
            }
#endif
            for (; k<valid; ++k) {
                size_t offset=2*(start+block+k);
                int64_t ar=iq[offset], ai=iq[offset+1];
                energy[k]+=ar*ar+ai*ai;
                ++support[k];
                if (k<paired) {
                    int64_t br=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG];
                    int64_t bi=iq[offset+2*LEO_PRESENCE_DIFFERENTIAL_LAG+1];
                    real[k]+=ar*br+ai*bi; imag[k]+=ar*bi-ai*br;
                    ++diff_support[k];
                }
            }
        }
        for (size_t k=0; k<width; ++k) {
            w->power_native_folded[block+k]=(double)energy[k];
            w->diff_folded[block+k]=(double)real[k]+I*(double)imag[k];
            w->support[block+k]=support[k];
            w->diff_support[block+k]=diff_support[k];
        }
    }
}
