/* Research FP32 dot products; support, template construction and normalization
 * stay FP64. Four lanes are explicit on both host and ARM for qualification. */
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
static void opt_diff_dot(const float *x, const float *t, size_t n,
    float real[4], float imag[4], float power_sum[4])
{
    size_t k=0;
#if defined(__ARM_NEON)
    float32x4_t r=vld1q_f32(real), i=vld1q_f32(imag), p=vld1q_f32(power_sum);
    for(; k+3<n; k+=4) {
        float32x4x3_t a=vld3q_f32(x+3*k), b=vld3q_f32(t+3*k);
        r=vaddq_f32(r,vaddq_f32(vmulq_f32(a.val[0],b.val[0]),vmulq_f32(a.val[1],b.val[1])));
        i=vaddq_f32(i,vsubq_f32(vmulq_f32(a.val[1],b.val[0]),vmulq_f32(a.val[0],b.val[1])));
        p=vaddq_f32(p,vmulq_f32(a.val[2],b.val[2]));
    }
    vst1q_f32(real,r);vst1q_f32(imag,i);vst1q_f32(power_sum,p);
#else
    for(; k+3<n; k+=4) for(size_t j=0;j<4;++j) {
        size_t z=3*(k+j);
        real[j]+=x[z]*t[z]+x[z+1]*t[z+1];
        imag[j]+=x[z+1]*t[z]-x[z]*t[z+1];
        power_sum[j]+=x[z+2]*t[z+2];
    }
#endif
    for(;k<n;++k) {
        size_t z=3*k;
        real[0]+=x[z]*t[z]+x[z+1]*t[z+1];
        imag[0]+=x[z+1]*t[z]-x[z]*t[z+1];
        power_sum[0]+=x[z+2]*t[z+2];
    }
}

static double opt_diff_cell(leo_presence_workspace *w, size_t epoch,
    double power_norm, double diff_norm)
{
    float real[4]={0},imag[4]={0},power_sum[4]={0};
    size_t split=w->n-epoch;
    opt_diff_dot(w->opt_fold+3*epoch,w->opt_template,split,real,imag,power_sum);
    opt_diff_dot(w->opt_fold,w->opt_template+3*split,epoch,real,imag,power_sum);
    double r=0,i=0,p=0;
    for(int k=0;k<4;++k) {r+=real[k];i+=imag[k];p+=power_sum[k];}
    return (diff_norm>0 ? magnitude(r+I*i)/diff_norm : 0)+
        (power_norm>0 ? (LEO_PRESENCE_DIFFERENTIAL_POWER_MILLI/1000.0)*p/power_norm : 0);
}
