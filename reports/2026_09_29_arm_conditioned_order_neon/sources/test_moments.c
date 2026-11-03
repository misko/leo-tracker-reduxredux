static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t state=0x19e82a1du;
static float random_float(void) { state=1664525u*state+1013904223u; return (float)((state>>8)*0x1p-23-0.5); }

static double check(uint32_t rate, int extreme)
{
    size_t n=(rate+375)/750;
    float *weighted=calloc(2*n,sizeof(*weighted));
    assert(weighted);
    double l1=0;
    for (size_t k=0;k<n;++k) {
        float re=extreme ? ((k&1)?32767.f:-32768.f) : random_float();
        float im=extreme ? ((k&2)?32767.f:-32768.f) : random_float();
        weighted[2*k]=re; weighted[2*k+1]=im; l1+=hypot(re,im);
    }
    float got[64]; conditioned_moment_magnitudes(weighted,n,rate,41,got);
    double maximum=0;
    for(int f=0;f<41;++f) {
        double complex exact=0;
        for(size_t k=0;k<n;++k)
            exact+=(weighted[2*k]+I*weighted[2*k+1])*rotate(-TAU*100.0*f*k/rate);
        double error=fabs(got[f]-magnitude(exact))/l1;
        if(error>maximum) maximum=error;
    }
    free(weighted); return maximum;
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    double maximum=0;
    for(int r=0;r<4;++r) for(int extreme=0;extreme<2;++extreme) {
        double error=check(rates[r],extreme);
        if(error>maximum) maximum=error;
    }
    /* This finite test bounds observed normalized magnitude error.  The
     * runtime recheck guard remains deliberately larger. */
    assert(maximum<CONDITIONED_MOMENT_GUARD);
    printf("conditioned moments passed: all rates random/extreme max-normalized-error %.9g guard %.9g\n",
        maximum,CONDITIONED_MOMENT_GUARD);
    return 0;
}
