#define _GNU_SOURCE
#include <assert.h>
#include <complex.h>
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#include <sched.h>
#endif

enum { FILTERS=132, OUTPUTS=8192, MAX_TAPS=44, MAX_FFT=256 };
static uint32_t rng=UINT32_C(0x67e21a95);
static float random_float(void) {
    rng=rng*UINT32_C(1664525)+UINT32_C(1013904223);
    return (int32_t)(rng>>9)*0x1p-22f-1.0f;
}
static double now(void) {
    struct timespec t; assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));
    return t.tv_sec+t.tv_nsec*1e-9;
}
static double median3(double v[3]) { if(v[0]>v[1]){double x=v[0];v[0]=v[1];v[1]=x;}
    if(v[1]>v[2]){double x=v[1];v[1]=v[2];v[2]=x;}
    if(v[0]>v[1]){double x=v[0];v[0]=v[1];v[1]=x;}return v[1]; }

/* The same complex multiply grouping as coarse_float_add, with frequency as
 * the NEON lane. Output is the production epoch-major 12-float grid. */
#pragma GCC push_options
#pragma GCC optimize ("no-prefetch-loop-arrays")
#if defined(__ARM_NEON)
static float32x4_t direct_magnitude(float32x4_t r,float32x4_t i) {
    float32x4_t s=vaddq_f32(vmulq_f32(r,r),vmulq_f32(i,i));
    float32x4_t safe=vbslq_f32(vceqq_f32(s,vdupq_n_f32(0)),vdupq_n_f32(1),s);
    float32x4_t q=vrsqrteq_f32(safe);
    q=vmulq_f32(q,vrsqrtsq_f32(vmulq_f32(safe,q),q));
    q=vmulq_f32(q,vrsqrtsq_f32(vmulq_f32(safe,q),q));
    return vmulq_f32(s,q);
}
#endif
static void direct_bank(const float complex *x,const float *real,const float *imag,int taps,
    int outputs,float *out)
{
    memset(out,0,sizeof(*out)*(size_t)outputs*12);
    for(int symbol=0;symbol<12;++symbol) for(int p=0;p<outputs;++p) {
#if defined(__ARM_NEON)
        float32x4_t r0=vdupq_n_f32(0),r1=r0,r2=r0,i0=r0,i1=r0,i2=r0;
        for(int k=0;k<taps;++k) {
            float32x4_t xr=vdupq_n_f32(crealf(x[p+k]));
            float32x4_t xi=vdupq_n_f32(cimagf(x[p+k]));
#define ACC(lane) do { float32x4_t rr=vld1q_f32(real+(symbol*taps+k)*12+4*lane); \
    float32x4_t ri=vld1q_f32(imag+(symbol*taps+k)*12+4*lane); \
    r##lane=vaddq_f32(r##lane,vaddq_f32(vmulq_f32(xr,rr),vmulq_f32(xi,ri))); \
    i##lane=vaddq_f32(i##lane,vsubq_f32(vmulq_f32(xi,rr),vmulq_f32(xr,ri))); }while(0)
            ACC(0);ACC(1);ACC(2);
#undef ACC
        }
        float *dst=out+12*p;
        vst1q_f32(dst,vaddq_f32(vld1q_f32(dst),direct_magnitude(r0,i0)));
        vst1q_f32(dst+4,vaddq_f32(vld1q_f32(dst+4),direct_magnitude(r1,i1)));
        vst1q_f32(dst+8,vaddq_f32(vld1q_f32(dst+8),direct_magnitude(r2,i2)));
#else
        for(int f=0;f<11;++f) { float r=0,i=0;
            for(int k=0;k<taps;++k) { float xr=crealf(x[p+k]),xi=cimagf(x[p+k]);
                float rr=real[(symbol*taps+k)*12+f];
                float ri=imag[(symbol*taps+k)*12+f];
                r+=xr*rr+xi*ri;i+=xi*rr-xr*ri; }
            out[12*p+f]+=hypotf(r,i);
        }
#endif
    }
}
#pragma GCC pop_options

typedef struct { int n,taps,step; fftwf_complex *in,*freq,*work,*kernels;
    fftwf_plan forward,inverse; } bank;
static void bank_init(bank *b,const float complex *h,int taps,int n) {
    memset(b,0,sizeof(*b));b->n=n;b->taps=taps;b->step=n-taps+1;
    b->in=fftwf_malloc(sizeof(*b->in)*n);b->freq=fftwf_malloc(sizeof(*b->freq)*n);
    b->work=fftwf_malloc(sizeof(*b->work)*n);b->kernels=fftwf_malloc(sizeof(*b->kernels)*n*FILTERS);
    assert(b->in&&b->freq&&b->work&&b->kernels);
    b->forward=fftwf_plan_dft_1d(n,b->in,b->freq,FFTW_FORWARD,FFTW_MEASURE);
    b->inverse=fftwf_plan_dft_1d(n,b->work,b->in,FFTW_BACKWARD,FFTW_MEASURE);
    assert(b->forward&&b->inverse);
    for(int f=0;f<FILTERS;++f) { memset(b->in,0,sizeof(*b->in)*n);
        for(int k=0;k<taps;++k) { float complex v=conjf(h[f*taps+(taps-1-k)]);
            b->in[k]=v; }
        fftwf_execute(b->forward);memcpy(b->kernels+f*n,b->freq,sizeof(*b->freq)*n); }
}
static void bank_destroy(bank *b) { fftwf_destroy_plan(b->forward);fftwf_destroy_plan(b->inverse);
    fftwf_free(b->kernels);fftwf_free(b->work);fftwf_free(b->freq);fftwf_free(b->in); }
static void fft_bank(bank *b,const float complex *x,int outputs,float *out) {
    memset(out,0,sizeof(*out)*(size_t)outputs*12);
    for(int base=0;base<outputs;base+=b->step) { int count=outputs-base;
        if(count>b->step)count=b->step;
        memset(b->in,0,sizeof(*b->in)*b->n);
        int available=outputs+b->taps-1-base;if(available>b->n)available=b->n;
        for(int k=0;k<available;++k)b->in[k]=x[base+k];
        fftwf_execute(b->forward);
        for(int f=0;f<FILTERS;++f) {
#if defined(__ARM_NEON)
            for(int k=0;k<b->n;k+=4) {
                float32x4x2_t a=vld2q_f32((float *)(b->freq+k));
                float32x4x2_t z=vld2q_f32((float *)(b->kernels+f*b->n+k));
                float32x4x2_t product;
                product.val[0]=vsubq_f32(vmulq_f32(a.val[0],z.val[0]),
                    vmulq_f32(a.val[1],z.val[1]));
                product.val[1]=vaddq_f32(vmulq_f32(a.val[0],z.val[1]),
                    vmulq_f32(a.val[1],z.val[0]));
                vst2q_f32((float *)(b->work+k),product);
            }
#else
            for(int k=0;k<b->n;++k)b->work[k]=b->freq[k]*b->kernels[f*b->n+k];
#endif
            fftwf_execute(b->inverse);
#if defined(__ARM_NEON)
            int j=0;float32x4_t scale=vdupq_n_f32(1.0f/b->n);
            for(;j+3<count;j+=4) { float32x4x2_t z=vld2q_f32((float *)(b->in+j+b->taps-1));
                float32x4_t m=vmulq_f32(direct_magnitude(z.val[0],z.val[1]),scale);
                float mv[4];vst1q_f32(mv,m);
                for(int lane=0;lane<4;++lane)out[12*(base+j+lane)+(f%11)]+=mv[lane]; }
            for(;j<count;++j) { float r=crealf(b->in[j+b->taps-1])/b->n;
                float i=cimagf(b->in[j+b->taps-1])/b->n;
                out[12*(base+j)+(f%11)]+=hypotf(r,i); }
#else
            for(int j=0;j<count;++j) { float r=crealf(b->in[j+b->taps-1])/b->n;
                float i=cimagf(b->in[j+b->taps-1])/b->n;
                out[12*(base+j)+(f%11)]+=hypotf(r,i); }
#endif
        }
    }
}
static void compare(const float *a,const float *b,double *max_norm,double *rms) {
    double worst=0,sum=0,den=0;for(size_t k=0;k<(size_t)12*OUTPUTS;++k) {
        double d=fabs((double)a[k]-b[k]);double scale=fmax(fabs((double)a[k]),1e-6);
        if(d/scale>worst)worst=d/scale;
        sum+=d*d;den+=a[k]*a[k]; }
    *max_norm=worst;*rms=sqrt(sum/fmax(den,1e-30));assert(isfinite(worst)&&isfinite(*rms));
}
int main(void) {
#if defined(__ARM_NEON)
    cpu_set_t allowed;CPU_ZERO(&allowed);CPU_SET(0,&allowed);
    assert(!sched_setaffinity(0,sizeof(allowed),&allowed));
#endif
    float complex *x=calloc(OUTPUTS+MAX_TAPS-1,sizeof(*x));
    float complex *h=calloc(FILTERS*MAX_TAPS,sizeof(*h));
    float *direct=calloc((size_t)12*OUTPUTS,sizeof(*direct));
    float *actual=calloc((size_t)12*OUTPUTS,sizeof(*actual));assert(x&&h&&direct&&actual);
    for(int k=0;k<OUTPUTS+MAX_TAPS-1;++k)x[k]=random_float()+I*random_float();
    for(int k=0;k<FILTERS*MAX_TAPS;++k)h[k]=random_float()+I*random_float();
    const int taps_list[]={11,22,33,44},sizes[]={64,128,256};
    puts("scope=deterministic-synthetic filters=132 outputs=8192 repetitions=3 median=cpu-time prepack=excluded kernel_spectra=excluded planning=excluded");
    puts("comparison=qualified-12-lane-direct-vs-132-exposed-filter-fft lane11_is_zero_padding");
    for(int ti=0;ti<4;++ti) { int taps=taps_list[ti];
        /* Repack because each configuration has a distinct compact stride. */
        float complex *hc=calloc(FILTERS*taps,sizeof(*hc));assert(hc);
        float *real=calloc((size_t)12*taps*12,sizeof(*real));
        float *imag=calloc((size_t)12*taps*12,sizeof(*imag));assert(real&&imag);
        for(int f=0;f<FILTERS;++f)memcpy(hc+f*taps,h+f*MAX_TAPS,sizeof(*hc)*taps);
        for(int symbol=0;symbol<12;++symbol)for(int k=0;k<taps;++k)for(int f=0;f<11;++f){
            real[(symbol*taps+k)*12+f]=crealf(hc[(symbol*11+f)*taps+k]);
            imag[(symbol*taps+k)*12+f]=cimagf(hc[(symbol*11+f)*taps+k]); }
        double dt[3];for(int rep=0;rep<3;++rep){double begin=now();direct_bank(x,real,imag,taps,OUTPUTS,direct);dt[rep]=now()-begin;}
        double direct_s=median3(dt);
        for(int si=0;si<3;++si) { bank b;double plan=now();bank_init(&b,hc,taps,sizes[si]);plan=now()-plan;
            for(int rep=0;rep<3;++rep){double begin=now();fft_bank(&b,x,OUTPUTS,actual);dt[rep]=now()-begin;}
            double fft_s=median3(dt);
            double max_norm,rms;compare(direct,actual,&max_norm,&rms);
            printf("taps=%d fft=%d direct_ms=%.3f fft_ms=%.3f plan_ms=%.3f speedup=%.4f max_norm=%.9g rms=%.9g\n",
                taps,sizes[si],direct_s*1000,fft_s*1000,plan*1000,direct_s/fft_s,max_norm,rms);
            assert(max_norm<0.02&&rms<2e-5);bank_destroy(&b); }
        free(imag);free(real);free(hc);
    }
    memset(x,0,sizeof(*x)*(OUTPUTS+MAX_TAPS-1));
    { bank b;bank_init(&b,h,44,256);fft_bank(&b,x,OUTPUTS,actual);
      for(size_t k=0;k<(size_t)12*OUTPUTS;++k)assert(actual[k]==0);
      bank_destroy(&b); }
    puts("zero=pass");x[0]=1;
    float *real=calloc((size_t)12*44*12,sizeof(*real)),*imag=calloc((size_t)12*44*12,sizeof(*imag));
    assert(real&&imag);for(int s=0;s<12;++s)for(int k=0;k<44;++k)for(int f=0;f<11;++f){
        real[(s*44+k)*12+f]=crealf(h[(s*11+f)*44+k]);imag[(s*44+k)*12+f]=cimagf(h[(s*11+f)*44+k]);}
    direct_bank(x,real,imag,44,OUTPUTS,direct);
    { bank b;double max_norm,rms,max_abs=0;bank_init(&b,h,44,256);fft_bank(&b,x,OUTPUTS,actual);
      compare(direct,actual,&max_norm,&rms);
      for(size_t k=0;k<(size_t)12*OUTPUTS;++k)
          max_abs=fmax(max_abs,fabs((double)direct[k]-actual[k]));
      assert(max_abs<1e-5&&rms<2e-5);
      printf("impulse=pass max_abs=%.9g rms=%.9g\n",max_abs,rms);bank_destroy(&b); }
    free(imag);free(real);free(actual);free(direct);free(h);free(x);return 0;
}
