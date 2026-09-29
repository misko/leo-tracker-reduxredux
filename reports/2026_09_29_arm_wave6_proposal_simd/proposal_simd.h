/* Independent four-bin arithmetic; no reduction reassociation or precision change.
 * Cortex-A9 NEON flushes subnormals, so full-range parity is explicitly not claimed.
 */
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif
static void proposal_product(const fftwf_complex *a,const fftwf_complex *b,
                             fftwf_complex *out,size_t n) {
    size_t k=0;
#ifdef __ARM_NEON
    for(;k+4<=n;k+=4){
        float32x4x2_t av=vld2q_f32((const float *)(a+k));
        float32x4x2_t bv=vld2q_f32((const float *)(b+k)),v;
        v.val[0]=vaddq_f32(vmulq_f32(av.val[0],bv.val[0]),vmulq_f32(av.val[1],bv.val[1]));
        v.val[1]=vsubq_f32(vmulq_f32(av.val[1],bv.val[0]),vmulq_f32(av.val[0],bv.val[1]));
        vst2q_f32((float *)(out+k),v);
    }
#endif
    for(;k<n;k++){
        float ar=a[k][0],ai=a[k][1],br=b[k][0],bi=b[k][1];
        out[k][0]=ar*br+ai*bi;out[k][1]=ai*br-ar*bi;
    }
}
static void proposal_scores(const fftwf_complex *a,float *out,size_t n,float scale,int method){
    size_t k=0;
#ifdef __ARM_NEON
    for(;k+4<=n;k+=4){
        float32x4x2_t av=vld2q_f32((const float *)(a+k));
        float32x4_t re=vmulq_n_f32(av.val[0],scale),v=re;
        if(method<3){float32x4_t im=vmulq_n_f32(av.val[1],scale);
            v=vaddq_f32(vmulq_f32(re,re),vmulq_f32(im,im));}
        vst1q_f32(out+k,v);
    }
#endif
    for(;k<n;k++)out[k]=method<3?rank_squared_magnitude(a[k][0],a[k][1],scale):a[k][0]*scale;
}
