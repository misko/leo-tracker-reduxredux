#include "decimated_fir.h"
#include <math.h>
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void leo_decimated_filter(float h[LEO_DECIMATED_TAPS])
{
    double sum=0,cutoff=.09;
    for(int k=0;k<LEO_DECIMATED_TAPS;k++) {
        double q=k-(LEO_DECIMATED_TAPS-1)*.5;
        double sinc=q==0?2*cutoff:sin(2*M_PI*cutoff*q)/(M_PI*q);
        double window=.54-.46*cos(2*M_PI*k/(LEO_DECIMATED_TAPS-1));
        h[k]=(float)(sinc*window);sum+=h[k];
    }
    for(int k=0;k<LEO_DECIMATED_TAPS;k++)h[k]/=(float)sum;
}

void leo_decimated_modulate(const float h[LEO_DECIMATED_TAPS],double rate,
    double center,float complex mh[LEO_DECIMATED_TAPS],float complex *step)
{
    for(int t=0;t<LEO_DECIMATED_TAPS;t++)
        mh[t]=h[t]*(float complex)cexp(I*2*M_PI*center*t/rate);
    *step=(float complex)cexp(-I*2*M_PI*center*LEO_DECIMATION/rate);
}

size_t leo_decimate_scalar(const float complex *x,size_t n,
    const float complex mh[LEO_DECIMATED_TAPS],float complex step,float complex *out)
{
    size_t m=n/LEO_DECIMATION;float complex osc=1;
    for(size_t j=0;j<m;j++) {
        float complex total=0;size_t at=LEO_DECIMATION*j;
        for(int t=0;t<LEO_DECIMATED_TAPS;t++) {
            size_t q=at>=(size_t)t?at-(size_t)t:at+n-(size_t)t;
            total+=x[q]*mh[t];
        }
        out[j]=total*osc;osc*=step;
    }
    return m;
}

#ifdef __ARM_NEON
static float32x4_t reverse4(float32x4_t v)
{
    v=vrev64q_f32(v);return vcombine_f32(vget_high_f32(v),vget_low_f32(v));
}
#endif

size_t leo_decimate_neon(const float complex *x,size_t n,
    const float complex mh[LEO_DECIMATED_TAPS],float complex step,float complex *out)
{
#ifndef __ARM_NEON
    return leo_decimate_scalar(x,n,mh,step,out);
#else
    size_t m=n/LEO_DECIMATION,j=0;float complex osc=1;
    /* The first five outputs wrap. Keep them scalar so every vector load below
     * lies wholly inside [0,n); this also covers all short/partial inputs. */
    for(;j<m&&LEO_DECIMATION*j<LEO_DECIMATED_TAPS-1;j++) {
        float complex total=0;size_t at=LEO_DECIMATION*j;
        for(int t=0;t<LEO_DECIMATED_TAPS;t++) {
            size_t q=at>=(size_t)t?at-(size_t)t:at+n-(size_t)t;
            total+=x[q]*mh[t];
        }
        out[j]=total*osc;osc*=step;
    }
    for(;j<m;j++) {
        size_t at=LEO_DECIMATION*j;float32x4_t sr=vdupq_n_f32(0),si=sr;
        for(int t=0;t<LEO_DECIMATED_TAPS;t+=4) {
            const float *xp=(const float *)(x+at-(size_t)t-3);
            float32x2x4_t xv=vld4_f32(xp); /* two complex pairs per structure */
            float32x4_t xr={xv.val[0][0],xv.val[2][0],xv.val[0][1],xv.val[2][1]};
            float32x4_t xi={xv.val[1][0],xv.val[3][0],xv.val[1][1],xv.val[3][1]};
            xr=reverse4(xr);xi=reverse4(xi);
            float32x4x2_t hv=vld2q_f32((const float *)(mh+t));
            sr=vmlaq_f32(sr,xr,hv.val[0]);sr=vmlsq_f32(sr,xi,hv.val[1]);
            si=vmlaq_f32(si,xr,hv.val[1]);si=vmlaq_f32(si,xi,hv.val[0]);
        }
        float rr[4],ii[4];vst1q_f32(rr,sr);vst1q_f32(ii,si);
        float complex total=(rr[0]+rr[1]+rr[2]+rr[3])+I*(ii[0]+ii[1]+ii[2]+ii[3]);
        out[j]=total*osc;osc*=step;
    }
    return m;
#endif
}
