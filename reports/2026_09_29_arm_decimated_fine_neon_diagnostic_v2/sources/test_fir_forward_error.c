#include "decimated_fir.h"
#include <complex.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static double gamma_n(int n)
{
    const double u=0.5*FLT_EPSILON;
    return n*u/(1.0-n*u);
}

static int check(uint32_t rate)
{
    size_t n=rate/500,m=n/LEO_DECIMATION;
    float complex *x=calloc(n,sizeof(*x)),*scalar=calloc(m,sizeof(*scalar)),*neon=calloc(m,sizeof(*neon));
    if(!x||!scalar||!neon)return 2;
    for(size_t k=0;k<n;k++)x[k]=(k&1)?(32767.0f-I*32768.0f):(-32768.0f+I*32767.0f);
    float h[LEO_DECIMATED_TAPS],mh_l1=0.0f;float complex mh[LEO_DECIMATED_TAPS],step,osc=1.0f;
    leo_decimated_filter(h);leo_decimated_modulate(h,rate,-80000,mh,&step);
    for(int t=0;t<LEO_DECIMATED_TAPS;t++)mh_l1+=cabsf(mh[t]);
    leo_decimate_scalar(x,n,mh,step,scalar);leo_decimate_neon(x,n,mh,step,neon);
    double max_scalar_ratio=0,max_neon_ratio=0,max_pair_error=0,max_old_ratio=0;
    size_t worst=0;int old_failures=0;
    for(size_t j=0;j<m;j++) {
        size_t at=LEO_DECIMATION*j;double complex sum=0;double weighted_l1=0;
        for(int t=0;t<LEO_DECIMATED_TAPS;t++) {
            size_t q=at>=(size_t)t?at-(size_t)t:at+n-(size_t)t;
            double xr=crealf(x[q]),xi=cimagf(x[q]),hr=crealf(mh[t]),hi=cimagf(mh[t]);
            sum+=(xr+I*xi)*(hr+I*hi);
            weighted_l1+=fabs(xr*hr)+fabs(xi*hi)+fabs(xr*hi)+fabs(xi*hr);
        }
        double complex oracle=sum*(double complex)osc;
        /* Each component has at most two rounded products per complex product,
         * 24 accumulation updates, a four-lane reduction, and the final
         * complex multiply.  gamma_64 times the componentwise product L1 plus
         * gamma_4 for the final multiply is a conservative FP32 forward bound
         * for both accumulation trees. */
        double bound=gamma_n(64)*weighted_l1+gamma_n(4)*cabs(sum)*cabsf(osc)+DBL_EPSILON;
        double se=cabs((double complex)scalar[j]-oracle),ne=cabs((double complex)neon[j]-oracle);
        double pe=cabsf(scalar[j]-neon[j]);double old=pe/(3e-6*fmax(1.0,cabsf(scalar[j])));
        if(se>bound||ne>bound) {
            fprintf(stderr,"BOUND FAIL rate=%u index=%zu scalar_error=%.17g neon_error=%.17g bound=%.17g weighted_l1=%.17g\n",rate,j,se,ne,bound,weighted_l1);
            free(neon);free(scalar);free(x);return 1;
        }
        if(old>1.0)old_failures++;
        if(ne/bound>max_neon_ratio){max_neon_ratio=ne/bound;worst=j;}
        if(se/bound>max_scalar_ratio)max_scalar_ratio=se/bound;
        if(pe>max_pair_error)max_pair_error=pe;
        if(old>max_old_ratio)max_old_ratio=old;
        osc*=step;
    }
    printf("rate=%u outputs=%zu old_tolerance_failures=%d max_old_ratio=%.9g max_pair_error=%.9g max_scalar_bound_ratio=%.9g max_neon_bound_ratio=%.9g worst_neon_index=%zu filter_l1=%.9g\n",
        rate,m,old_failures,max_old_ratio,max_pair_error,max_scalar_ratio,max_neon_ratio,worst,mh_l1);
    free(neon);free(scalar);free(x);return 0;
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};int failed=0;
    for(size_t k=0;k<sizeof(rates)/sizeof(rates[0]);k++)failed|=check(rates[k]);
    return failed;
}
