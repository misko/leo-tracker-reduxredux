#include "decimated_fir.h"
#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static int diagnose(const char *pattern,const float complex *x,size_t n,
    double rate,double center)
{
    size_t m=n/LEO_DECIMATION;
    float h[LEO_DECIMATED_TAPS],mh_l1=0.0f;
    float complex mh[LEO_DECIMATED_TAPS],step;
    float complex *scalar=calloc(m,sizeof(*scalar));
    float complex *neon=calloc(m,sizeof(*neon));
    if(!scalar||!neon)return 2;
    leo_decimated_filter(h);
    leo_decimated_modulate(h,rate,center,mh,&step);
    for(int t=0;t<LEO_DECIMATED_TAPS;t++)mh_l1+=cabsf(mh[t]);
    leo_decimate_scalar(x,n,mh,step,scalar);
    leo_decimate_neon(x,n,mh,step,neon);
    for(size_t k=0;k<m;k++) {
        double input_l1=0.0;
        size_t at=LEO_DECIMATION*k;
        for(int t=0;t<LEO_DECIMATED_TAPS;t++) {
            size_t q=at>=(size_t)t?at-(size_t)t:at+n-(size_t)t;
            input_l1+=cabsf(x[q]);
        }
        double error=cabsf(scalar[k]-neon[k]);
        double scale=fmax(1.0,cabsf(scalar[k]));
        if(error>3e-6*scale) {
            printf("FAIL pattern=%s rate=%.0f center=%.0f n=%zu index=%zu "
                "scalar=(%.9g,%.9g) neon=(%.9g,%.9g) error=%.17g "
                "bound=%.17g output_scale=%.17g input_l1=%.17g mh_l1=%.9g\n",
                pattern,rate,center,n,k,crealf(scalar[k]),cimagf(scalar[k]),
                crealf(neon[k]),cimagf(neon[k]),error,3e-6*scale,scale,
                input_l1,mh_l1);
            free(neon);free(scalar);return 1;
        }
    }
    printf("PASS pattern=%s rate=%.0f center=%.0f n=%zu outputs=%zu\n",
        pattern,rate,center,n,m);
    free(neon);free(scalar);return 0;
}

static int run_rate(uint32_t rate)
{
    size_t n=rate/500;
    float complex *x=calloc(n,sizeof(*x));
    if(!x)return 2;
    int failed=diagnose("zero",x,n,rate,80000);
    for(size_t k=0;k<n;k++)
        x[k]=(k&1)?(32767.0f-I*32768.0f):(-32768.0f+I*32767.0f);
    failed|=diagnose("alternating-fullscale",x,n,rate,-80000);
    memset(x,0,n*sizeof(*x));x[0]=1;x[n/2]=-I;
    failed|=diagnose("two-impulse",x,n,rate,0);
    const double center=80000,first=37000,second=-61000,alias=520000;
    for(size_t k=0;k<n;k++) {
        double a=2*M_PI*(center+first)*k/rate;
        double b=2*M_PI*(center+second)*k/rate;
        double c=2*M_PI*(center+alias)*k/rate;
        x[k]=(float complex)(cexp(I*a)+.7*cexp(I*b)+.8*cexp(I*c));
    }
    failed|=diagnose("three-tone",x,n,rate,center);
    failed|=diagnose("three-tone-partial",x,n-1,rate,center);
    failed|=diagnose("three-tone-short",x,29,rate,center);
    free(x);return failed;
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    int failed=0;
    for(size_t k=0;k<sizeof(rates)/sizeof(rates[0]);k++)failed|=run_rate(rates[k]);
    return failed?1:0;
}
