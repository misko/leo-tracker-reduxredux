#include "decimated_fir.h"
#include <assert.h>
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static double response(const float *h,double f,double rate)
{double complex z=0;for(int k=0;k<LEO_DECIMATED_TAPS;k++)z+=h[k]*cexp(-I*2*M_PI*f*k/rate);return cabs(z);}
static double complex direct(const float complex *x,size_t n,double rate,double f)
{double complex z=0;for(size_t k=0;k<n;k++)z+=(double complex)x[k]*cexp(-I*2*M_PI*f*k/rate);return z;}

static void compare_kernel(const float complex *x,size_t n,double rate,double center)
{
    size_t m=n/5;float h[24];float complex mh[24],step;
    float complex *a=calloc(m,sizeof(*a)),*b=calloc(m,sizeof(*b));assert(a&&b);
    leo_decimated_filter(h);leo_decimated_modulate(h,rate,center,mh,&step);
    assert(leo_decimate_scalar(x,n,mh,step,a)==m&&leo_decimate_neon(x,n,mh,step,b)==m);
    for(size_t k=0;k<m;k++) {
        double scale=fmax(1.0,cabsf(a[k]));assert(cabsf(a[k]-b[k])<=3e-6*scale);
    }
    free(b);free(a);
}

static void run_rate(uint32_t rate)
{
    size_t n=rate/500,m=n/5;float complex *x=fftwf_alloc_complex(n),*d=fftwf_alloc_complex(m),*fft=fftwf_alloc_complex(m);assert(x&&d&&fft);
    memset(x,0,n*sizeof(*x));compare_kernel(x,n,rate,80000);
    for(size_t k=0;k<n;k++)x[k]=(k&1)?(32767.0f-I*32768.0f):(-32768.0f+I*32767.0f);
    compare_kernel(x,n,rate,-80000);
    memset(x,0,n*sizeof(*x));x[0]=1;x[n/2]=-I;compare_kernel(x,n,rate,0);
    const double center=80000,tones[]={37000,-61000};
    for(size_t k=0;k<n;k++){double a=2*M_PI*(center+tones[0])*k/rate,b=2*M_PI*(center+tones[1])*k/rate,c=2*M_PI*(center+520000)*k/rate;x[k]=(float complex)(cexp(I*a)+.7*cexp(I*b)+.8*cexp(I*c));}
    compare_kernel(x,n,rate,center);float h[24];float complex mh[24],step;leo_decimated_filter(h);leo_decimated_modulate(h,rate,center,mh,&step);leo_decimate_neon(x,n,mh,step,d);
    fftwf_plan p=fftwf_plan_dft_1d((int)m,(fftwf_complex*)d,(fftwf_complex*)fft,FFTW_FORWARD,FFTW_ESTIMATE);assert(p);fftwf_execute(p);
    for(int q=0;q<2;q++){int bin=(int)nearbyint(tones[q]/500);bin=(bin+(int)m)%(int)m;double estimate=5*cabs((double complex)fft[bin])/response(h,tones[q],rate),expected=cabs(direct(x,n,rate,center+tones[q]));assert(fabs(estimate-expected)<=.015*fmax(1.0,expected));}
    int alias=(int)nearbyint(20000.0/500);double aliased=5*cabs((double complex)fft[alias])/response(h,20000,rate),expected=cabs(direct(x,n,rate,center+20000));assert(fabs(aliased-expected)<=.08*n);
    fftwf_destroy_plan(p);
    /* Nonmultiple partial lengths exercise the scalar wrap prefix and the
     * final vector output without any full-frame read assumption. */
    compare_kernel(x,n-1,rate,center);compare_kernel(x,29,rate,center);
    fftwf_free(fft);fftwf_free(d);fftwf_free(x);
}

int main(void){const uint32_t rates[]={2500000,5000000,7500000,10000000};for(int k=0;k<4;k++)run_rate(rates[k]);puts("decimated NEON FIR passed: all rates zero/fullscale/impulse/tone/twotone/OOB alias/partial bounds");return 0;}
