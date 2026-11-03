static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x6d21b4c3u;
static float value(void){rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-24f-.5f);}

int main(void)
{
    double complex samples[64];float exact[128],control[128];
    for(int k=0;k<64;++k) {
        samples[k]=(k&1?-32768.0:32767.0)+I*(k&2?-32768.0:32767.0);
        exact[2*k]=value();exact[2*k+1]=value();control[2*k]=value();control[2*k+1]=value();
    }
    for(int n=1;n<=64;++n) {
        double complex got_e,got_c,ref_e=0,ref_c=0;
        glrt_float_symbol_dot(samples,0,0,n,exact,control,&got_e,&got_c);
        for(int k=0;k<n;++k) {
            float xr=(float)creal(samples[k]),xi=(float)cimag(samples[k]);
            ref_e+=(double)(float)(xr*exact[2*k]-xi*exact[2*k+1])+I*(double)(float)(xr*exact[2*k+1]+xi*exact[2*k]);
            ref_c+=(double)(float)(xr*control[2*k]-xi*control[2*k+1])+I*(double)(float)(xr*control[2*k+1]+xi*control[2*k]);
        }
        assert(isfinite(creal(got_e))&&isfinite(cimag(got_e))&&isfinite(creal(got_c))&&isfinite(cimag(got_c)));
        assert(cabs(got_e-ref_e)<=2.0*n);assert(cabs(got_c-ref_c)<=2.0*n);
    }
    puts("FP32 symbol dot passed: lengths 1..64, extreme CI16, stable four-lane tolerance");
}
