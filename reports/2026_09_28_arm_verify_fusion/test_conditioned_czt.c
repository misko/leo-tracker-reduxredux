#include "conditioned_czt.h"

#include <complex.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TAU 6.283185307179586476925286766559
#define MAX_N 13333

static uint32_t state=0x72a519d3u;
static double maximum_error;
static float random_float(void)
{
    state=1664525u*state+1013904223u;
    return ((float)(state>>8)*(1.0f/8388608.0f)-1.0f)*.25f;
}

static int trial(double rate, size_t n, int nf, double f0, int mode)
{
    static float x[2*MAX_N], got[64];
    if (n>MAX_N) return 1;
    for (size_t k=0;k<n;++k) {
        float re, im;
        if (mode==1) re=im=0;
        else if (mode==2) {
            double tone=TAU*1700.0*(double)k/rate;
            re=(float)cos(tone); im=(float)sin(tone);
        } else if (mode==3) {
            /* Equal coherent tones halfway around adjacent CZT bins exercise
             * a near tie without changing the all-bin error criterion. */
            double p0=TAU*1500.0*(double)k/rate;
            double p1=TAU*1600.0*(double)k/rate;
            re=(float)(cos(p0)+cos(p1)); im=(float)(sin(p0)+sin(p1));
        } else { re=random_float(); im=random_float(); }
        double phase=-TAU*f0*(double)k/rate;
        float cr=(float)cos(phase), ci=(float)sin(phase);
        x[2*k]=re*cr-im*ci; x[2*k+1]=re*ci+im*cr;
    }
    if (leo_conditioned_czt_magnitudes(x,n,rate,nf,got)) return 1;
    double scale=0;
    for (size_t k=0;k<n;++k) scale+=hypot(x[2*k],x[2*k+1]);
    if (scale<1) scale=1;
    for (int j=0;j<nf;++j) {
        double complex sum=0;
        for (size_t k=0;k<n;++k) {
            double phase=-TAU*100.0*j*(double)k/rate;
            sum+=(x[2*k]+I*x[2*k+1])*(cos(phase)+I*sin(phase));
        }
        double want=cabs(sum), error=fabs((double)got[j]-want)/scale;
        if (error>maximum_error) maximum_error=error;
        if (!isfinite(got[j]) || error>128.0*FLT_EPSILON) {
            fprintf(stderr,"rate %.0f n %zu nf %d f0 %.1f bin %d: got %.9g want %.17g normalized error %.9g\n",
                rate,n,nf,f0,j,got[j],want,error);
            return 1;
        }
    }
    return 0;
}

int main(void)
{
    const double rates[]={2500000,5000000,7500000,10000000};
    const size_t lengths[]={3333,6667,10000,13333};
    for (size_t r=0;r<sizeof(rates)/sizeof(*rates);++r) {
        if (trial(rates[r],lengths[r],1,17321.25,0) ||
            trial(rates[r],lengths[r],41,-31789.75,0) ||
            trial(rates[r],lengths[r],41,8123.5,1) ||
            trial(rates[r],lengths[r],41,0,2) ||
            trial(rates[r],lengths[r],41,0,3)) return 1;
    }
    float unused[65], input[2]={0};
    if (!leo_conditioned_czt_magnitudes(input,1,2500000,65,unused)) {
        fputs("unsupported bin count did not request fallback\n",stderr); return 1;
    }
    printf("conditioned CZT passed; max normalized FP64 error %.9g\n",maximum_error);
    return 0;
}
