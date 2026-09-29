#define _POSIX_C_SOURCE 200809L
#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif

enum { N = 3333, NF = 33, MAX_FRAMES = 16 };

__attribute__((noinline,noclone)) static double complex dot1(const float *a, const float *b, size_t n)
{
    double tr=0,ti=0;
    for(size_t s=0;s<n;s+=64){
        size_t e=s+64<n?s+64:n,k=s; float re[4]={0},im[4]={0};
#if defined(__ARM_NEON)
        float32x4_t vr=vdupq_n_f32(0),vi=vr;
        for(;k+3<e;k+=4){
            float32x4x2_t x=vld2q_f32(a+2*k),y=vld2q_f32(b+2*k);
            vr=vaddq_f32(vr,vsubq_f32(vmulq_f32(x.val[0],y.val[0]),vmulq_f32(x.val[1],y.val[1])));
            vi=vaddq_f32(vi,vaddq_f32(vmulq_f32(x.val[0],y.val[1]),vmulq_f32(x.val[1],y.val[0])));
        }
        vst1q_f32(re,vr);vst1q_f32(im,vi);
#else
        for(;k+3<e;k+=4)for(size_t j=0;j<4;++j){size_t z=2*(k+j);re[j]+=a[z]*b[z]-a[z+1]*b[z+1];im[j]+=a[z]*b[z+1]+a[z+1]*b[z];}
#endif
        for(;k<e;++k){re[0]+=a[2*k]*b[2*k]-a[2*k+1]*b[2*k+1];im[0]+=a[2*k]*b[2*k+1]+a[2*k+1]*b[2*k];}
        for(int j=0;j<4;++j){tr+=re[j];ti+=im[j];}
    }
    return tr+I*ti;
}

#define DEFINE_TILE(F) \
__attribute__((noinline,noclone)) static void dot##F(const float*a,const float*b,size_t n,double complex out[F]){ \
 double tr[F]={0},ti[F]={0}; \
 for(size_t s=0;s<n;s+=64){size_t e=s+64<n?s+64:n,k=s;float re[F][4]={{0}},im[F][4]={{0}}; \
 /* The ARM body intentionally matches the production four-bin kernel. */ \
 /* clang-format off */ \
 ARM_BODY_##F \
 /* clang-format on */ \
 for(;k<e;++k)for(int f=0;f<F;++f){size_t x=2*k,y=2*((size_t)f*n+k);re[f][0]+=a[x]*b[y]-a[x+1]*b[y+1];im[f][0]+=a[x]*b[y+1]+a[x+1]*b[y];} \
 for(int f=0;f<F;++f)for(int j=0;j<4;++j){tr[f]+=re[f][j];ti[f]+=im[f][j];}} \
 for(int f=0;f<F;++f)out[f]=tr[f]+I*ti[f];}

#if defined(__ARM_NEON)
#define ARM_BODY_2 float32x4_t vr[2],vi[2];for(int f=0;f<2;++f)vr[f]=vi[f]=vdupq_n_f32(0);for(;k+3<e;k+=4){float32x4x2_t x=vld2q_f32(a+2*k);for(int f=0;f<2;++f){float32x4x2_t y=vld2q_f32(b+2*((size_t)f*n+k));vr[f]=vaddq_f32(vr[f],vsubq_f32(vmulq_f32(x.val[0],y.val[0]),vmulq_f32(x.val[1],y.val[1])));vi[f]=vaddq_f32(vi[f],vaddq_f32(vmulq_f32(x.val[0],y.val[1]),vmulq_f32(x.val[1],y.val[0])));}}for(int f=0;f<2;++f){vst1q_f32(re[f],vr[f]);vst1q_f32(im[f],vi[f]);}
#define ARM_BODY_4 float32x4_t vr[4],vi[4];for(int f=0;f<4;++f)vr[f]=vi[f]=vdupq_n_f32(0);for(;k+3<e;k+=4){float32x4x2_t x=vld2q_f32(a+2*k);for(int f=0;f<4;++f){float32x4x2_t y=vld2q_f32(b+2*((size_t)f*n+k));vr[f]=vaddq_f32(vr[f],vsubq_f32(vmulq_f32(x.val[0],y.val[0]),vmulq_f32(x.val[1],y.val[1])));vi[f]=vaddq_f32(vi[f],vaddq_f32(vmulq_f32(x.val[0],y.val[1]),vmulq_f32(x.val[1],y.val[0])));}}for(int f=0;f<4;++f){vst1q_f32(re[f],vr[f]);vst1q_f32(im[f],vi[f]);}
#else
#define ARM_BODY_2 for(;k+3<e;k+=4)for(int f=0;f<2;++f)for(size_t j=0;j<4;++j){size_t x=2*(k+j),y=2*((size_t)f*n+k+j);re[f][j]+=a[x]*b[y]-a[x+1]*b[y+1];im[f][j]+=a[x]*b[y+1]+a[x+1]*b[y];}
#define ARM_BODY_4 for(;k+3<e;k+=4)for(int f=0;f<4;++f)for(size_t j=0;j<4;++j){size_t x=2*(k+j),y=2*((size_t)f*n+k+j);re[f][j]+=a[x]*b[y]-a[x+1]*b[y+1];im[f][j]+=a[x]*b[y+1]+a[x+1]*b[y];}
#endif
DEFINE_TILE(2)
DEFINE_TILE(4)

static float *inputs,*offsets;
__attribute__((noinline,noclone)) static void scores(int kind,int frames,double out[NF]){
    memset(out,0,NF*sizeof(*out));
    for(int fr=0;fr<frames;++fr){
        const float*a=inputs+2*(size_t)fr*N;
        for(int f=0;f<NF;){
            double complex z[4];int width=kind==4&&f+3<NF?4:kind==2&&f+1<NF?2:1;
            if(width==4)dot4(a,offsets+2*(size_t)f*N,N,z);
            else if(width==2)dot2(a,offsets+2*(size_t)f*N,N,z);
            else z[0]=dot1(a,offsets+2*(size_t)f*N,N);
            for(int j=0;j<width;++j)out[f+j]+=cabs(z[j])/1234.567890123;
            f+=width;
        }
    }
    for(int f=0;f<NF;++f)out[f]/=frames;
}
static double now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+1e-9*t.tv_nsec;}
static uint32_t step(uint32_t*x){*x=*x*1664525u+1013904223u;return*x;}
int main(int argc,char**argv){
    int reps=argc>1?atoi(argv[1]):20;if(reps<1)return 2;
    inputs=malloc(2u*MAX_FRAMES*N*sizeof(float));offsets=malloc(2u*NF*N*sizeof(float));if(!inputs||!offsets)return 3;
    uint32_t x=0x6c656f32u;for(size_t i=0;i<2u*MAX_FRAMES*N;++i)inputs[i]=(int32_t)(step(&x)>>8)*(1.0f/8388608.0f);
    for(size_t i=0;i<2u*NF*N;++i)offsets[i]=(int32_t)(step(&x)>>8)*(1.0f/8388608.0f);
    for(int frames=15;frames<=16;++frames){
        double ref[NF],two[NF],four[NF];scores(1,frames,ref);scores(2,frames,two);scores(4,frames,four);
        int eq2=!memcmp(ref,two,sizeof ref),eq4=!memcmp(ref,four,sizeof ref);
        if(!eq2||!eq4){fprintf(stderr,"bitwise mismatch frames=%d tile2=%d tile4=%d\n",frames,eq2,eq4);return 4;}
        double sums[3]={0};
        for(int r=0;r<reps;++r)for(int q=0;q<3;++q){int kind=(r+q)%3==0?1:(r+q)%3==1?2:4;double out[NF],t=now();scores(kind,frames,out);sums[kind==1?0:kind==2?1:2]+=now()-t;}
        printf("{\"n\":%d,\"nf\":%d,\"frames\":%d,\"repetitions\":%d,\"bitwise_tile2\":true,\"bitwise_tile4\":true,\"scalar_cpu_ms\":%.6f,\"tile2_cpu_ms\":%.6f,\"tile4_cpu_ms\":%.6f}\n",N,NF,frames,reps,1e3*sums[0]/reps,1e3*sums[1]/reps,1e3*sums[2]/reps);
    }
    free(offsets);free(inputs);return 0;
}
