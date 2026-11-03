#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Include the implementation so this unit exercises the selected scalar/NEON
 * fold path without needing a public test-only API. */
#include "proposal_core.c"

static void compare_case(size_t n,int pattern)
{
    const size_t start=1,off=2,samples=start+off+n+5;
    int16_t *raw=calloc(samples*4,sizeof(*raw));
    fftwf_complex *fused[3],*reference[3];
    assert(raw);
    for(size_t q=0;q<samples*4;q++) {
        if(pattern==1) raw[q]=(q&1)?INT16_MIN:INT16_MAX;
        else if(pattern==2) raw[q]=(int16_t)((q*7919u)%65535u-32767);
    }
    for(int m=0;m<3;m++) {
        fused[m]=fftwf_alloc_complex(n);
        reference[m]=fftwf_alloc_complex(n);
        assert(fused[m]&&reference[m]);
        memset(fused[m],0,n*sizeof(*fused[m]));
        memset(reference[m],0,n*sizeof(*reference[m]));
    }
    /* Include a zero-length lag, unequal tails, and all 16 frame updates. */
    for(int frame=0;frame<FRAMES;frame++) {
        size_t valid[3]={n-(size_t)(frame%3),n-(size_t)(2+frame%4),
                         n-(size_t)(4+frame%5)};
        if(frame==0)valid[2]=0;
        fold_three(fused,raw,start,off,valid,1);
        for(int m=0;m<3;m++)
            fold_selected(reference[m],raw,start,off,valid[m],1,lags[m]);
    }
    for(int m=0;m<3;m++) {
        assert(!memcmp(fused[m],reference[m],n*sizeof(*fused[m])));
        fftwf_free(fused[m]);
        fftwf_free(reference[m]);
    }
    free(raw);
}

int main(void)
{
    const size_t lengths[]={2500000/750,5000000/750,7500000/750,10000000/750};
    for(size_t rate=0;rate<4;rate++)
        for(int pattern=0;pattern<3;pattern++)compare_case(lengths[rate],pattern);
    puts("fused lag fold exact: zero, extreme, unequal-tail, all-rate cases");
    return 0;
}
