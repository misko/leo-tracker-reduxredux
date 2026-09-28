#define _POSIX_C_SOURCE 200809L
#include "fft.h"
#include <assert.h>
#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

void leo_fft_forward_range(leo_fft *,const double complex *,size_t,size_t,size_t);

static uint64_t random_state=UINT64_C(0x9e3779b97f4a7c15);
static double random_unit(void)
{
    random_state^=random_state>>12; random_state^=random_state<<25;
    random_state^=random_state>>27;
    return (double)((random_state*UINT64_C(2685821657736338717))>>11)*0x1p-53;
}

static void compare_range(size_t n, size_t used, size_t first, size_t count,
    int pattern, int alias)
{
    leo_fft reference={0}, pruned={0};
    assert(!leo_fft_init(&reference,n) && !leo_fft_init(&pruned,n));
    double complex *input=calloc(n,sizeof(*input)); assert(input);
    if (pattern==0) input[used/3]=.75-I*.25;
    else if (pattern==1) for (size_t k=0;k<used;++k)
        input[k]=cexp(I*6.2831853071795864769*137*k/n);
    else for (size_t k=0;k<used;++k) if (k%3 && k%11)
        input[k]=(random_unit()-.5)+I*(random_unit()-.5);
    leo_fft_forward(&reference,input);
    const double complex *selected_input=input;
    if (alias) {
        memcpy(pruned.output,input,n*sizeof(*input));
        selected_input=pruned.output;
    }
    leo_fft_forward_range(&pruned,selected_input,used,first,count);
    size_t bin=first;
    for (size_t i=0;i<count;++i) {
        double error=cabs(pruned.output[bin]-reference.output[bin]);
        double scale=fmax(1,cabs(reference.output[bin]));
        assert(error<=2e-12*scale);
        if (++bin==n) bin=0;
    }
    free(input); leo_fft_free(&reference); leo_fft_free(&pruned);
}

static double milliseconds(void)
{
    struct timespec value; assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&value));
    return value.tv_sec*1000.0+value.tv_nsec/1e6;
}

int main(void)
{
    const size_t sizes[]={5000,10000,15000,20000};
    for (size_t s=0;s<4;++s) {
        size_t n=sizes[s], used=(size_t)nearbyint(n*2.0/3.0);
        compare_range(n,used,17,321,0,0);
        compare_range(n,used,n-109,321,1,0);
        compare_range(n,used,n-7,19,2,0);
        compare_range(n,used,31,321,2,1);
    }

    /* Modest host timing smoke tests. They are diagnostic, never pass gates. */
    for (size_t s=0;s<4;++s) {
        size_t n=sizes[s], used=(size_t)nearbyint(n*2.0/3.0);
        leo_fft full={0}, pruned={0};
        assert(!leo_fft_init(&full,n) && !leo_fft_init(&pruned,n));
        double complex *input=calloc(n,sizeof(*input)); assert(input);
        for (size_t k=0;k<used;++k)
            input[k]=(k%5 ? .25 : -.5)+I*(k%7 ? .125 : -.25);
        double start=milliseconds();
        for (int k=0;k<8;++k) leo_fft_forward(&full,input);
        double full_ms=milliseconds()-start;
        start=milliseconds();
        for (int k=0;k<8;++k)
            leo_fft_forward_range(&pruned,input,used,n-321,321);
        double pruned_ms=milliseconds()-start;
        printf("n=%zu full_ms=%.3f pruned_ms=%.3f ratio=%.3f\n",
            n,full_ms,pruned_ms,pruned_ms/full_ms);
        free(input); leo_fft_free(&full); leo_fft_free(&pruned);
    }
    return 0;
}
