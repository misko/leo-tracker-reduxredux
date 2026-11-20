#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
/* Experimental FP32 conditioned dot. Template/rotation construction, sample
 * energy, normalization, and final GLRT statistic retain FP64 arithmetic. */
static double complex opt_conditioned_dot(const float *a,const float *b,size_t n)
{
    float real[4]={0},imag[4]={0};size_t k=0;
#if defined(__ARM_NEON)
    float32x4_t re=vdupq_n_f32(0),im=re;
    for(;k+3<n;k+=4){
        float32x4x2_t x=vld2q_f32(a+2*k),y=vld2q_f32(b+2*k);
        re=vaddq_f32(re,vsubq_f32(vmulq_f32(x.val[0],y.val[0]),vmulq_f32(x.val[1],y.val[1])));
        im=vaddq_f32(im,vaddq_f32(vmulq_f32(x.val[0],y.val[1]),vmulq_f32(x.val[1],y.val[0])));
    }
    vst1q_f32(real,re);vst1q_f32(imag,im);
#else
    for(;k+3<n;k+=4)for(size_t j=0;j<4;++j){
        size_t z=2*(k+j);
        real[j]+=a[z]*b[z]-a[z+1]*b[z+1];
        imag[j]+=a[z]*b[z+1]+a[z+1]*b[z];
    }
#endif
    for(;k<n;++k){real[0]+=a[2*k]*b[2*k]-a[2*k+1]*b[2*k+1];
        imag[0]+=a[2*k]*b[2*k+1]+a[2*k+1]*b[2*k];}
    double r=0,i=0;for(int j=0;j<4;++j){r+=real[j];i+=imag[j];}
    return r+I*i;
}
