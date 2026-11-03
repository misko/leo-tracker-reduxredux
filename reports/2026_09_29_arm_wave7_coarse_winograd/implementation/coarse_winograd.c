#include "coarse_winograd.h"
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

void cw_prepare(const float hr[3][CW_CFO], const float hi[3][CW_CFO], cw_filters *o)
{
    for (int f=0;f<CW_CFO;++f) {
        float a=hr[0][f],b=hr[1][f],c=hr[2][f];
        float ai=hi[0][f],bi=hi[1][f],ci=hi[2][f];
        o->re[0][f]=a*.25f; o->im[0][f]=ai*.25f;
        o->re[1][f]=-(a+b+c)/6; o->im[1][f]=-(ai+bi+ci)/6;
        o->re[2][f]=(-a+b-c)/6; o->im[2][f]=(-ai+bi-ci)/6;
        o->re[3][f]=(a+2*b+4*c)/24; o->im[3][f]=(ai+2*bi+4*ci)/24;
        o->re[4][f]=(a-2*b+4*c)/24; o->im[4][f]=(ai-2*bi+4*ci)/24;
        o->re[5][f]=c; o->im[5][f]=ci;
    }
}

void cw_four(const float xr[6],const float xi[6],const cw_filters *h,
    float yr[4][CW_CFO],float yi[4][CW_CFO])
{
    float ur[6],ui[6];
#define BT(dst,z) do { \
 dst[0]=4*z[0]-5*z[2]+z[4]; dst[1]=-4*z[1]-4*z[2]+z[3]+z[4]; \
 dst[2]=4*z[1]-4*z[2]-z[3]+z[4]; dst[3]=-2*z[1]-z[2]+2*z[3]+z[4]; \
 dst[4]=2*z[1]-z[2]-2*z[3]+z[4]; dst[5]=4*z[1]-5*z[3]+z[5]; } while(0)
    BT(ur,xr); BT(ui,xi);
#undef BT
 #if defined(__ARM_NEON)
    for(int f=0;f<CW_CFO;f+=4) {
        float32x4_t mr[6],mi[6];
        for(int j=0;j<6;++j){float32x4_t ar=vld1q_f32(h->re[j]+f),ai=vld1q_f32(h->im[j]+f);mr[j]=vsubq_f32(vmulq_n_f32(ar,ur[j]),vmulq_n_f32(ai,ui[j]));mi[j]=vaddq_f32(vmulq_n_f32(ai,ur[j]),vmulq_n_f32(ar,ui[j]));}
#define NAT(dst,m) do { vst1q_f32(dst[0]+f,vaddq_f32(vaddq_f32(m[0],m[1]),vaddq_f32(m[2],vaddq_f32(m[3],m[4])))); \
 vst1q_f32(dst[1]+f,vaddq_f32(vsubq_f32(m[1],m[2]),vmulq_n_f32(vsubq_f32(m[3],m[4]),2))); \
 vst1q_f32(dst[2]+f,vaddq_f32(vaddq_f32(m[1],m[2]),vmulq_n_f32(vaddq_f32(m[3],m[4]),4))); \
 vst1q_f32(dst[3]+f,vaddq_f32(vaddq_f32(vsubq_f32(m[1],m[2]),vmulq_n_f32(vsubq_f32(m[3],m[4]),8)),m[5])); } while(0)
        NAT(yr,mr); NAT(yi,mi);
#undef NAT
    }
 #else
    for(int f=0;f<CW_CFO;++f) {
        float mr[6],mi[6];
        for(int j=0;j<6;++j){mr[j]=ur[j]*h->re[j][f]-ui[j]*h->im[j][f];mi[j]=ur[j]*h->im[j][f]+ui[j]*h->re[j][f];}
#define AT(dst,m) do { dst[0][f]=m[0]+m[1]+m[2]+m[3]+m[4]; \
 dst[1][f]=m[1]-m[2]+2*m[3]-2*m[4]; dst[2][f]=m[1]+m[2]+4*m[3]+4*m[4]; \
 dst[3][f]=m[1]-m[2]+8*m[3]-8*m[4]+m[5]; } while(0)
        AT(yr,mr);AT(yi,mi);
#undef AT
    }
 #endif
}

void cw_direct(const float xr[6],const float xi[6],const float hr[3][CW_CFO],
    const float hi[3][CW_CFO],float yr[4][CW_CFO],float yi[4][CW_CFO])
{
    for(int j=0;j<4;++j)for(int f=0;f<CW_CFO;++f){float ar=0,ai=0;for(int k=0;k<3;++k){ar+=xr[j+k]*hr[k][f]-xi[j+k]*hi[k][f];ai+=xr[j+k]*hi[k][f]+xi[j+k]*hr[k][f];}yr[j][f]=ar;yi[j][f]=ai;}
}
