#define _GNU_SOURCE
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "proposal_core.c"

static void run_rate(size_t rate,int extreme)
{
    size_t n=rate/750,count=rate/50,dwell=rate*120/1000;
    fftwf_complex *template=fftwf_alloc_complex(n); bank b;
    int16_t *raw=calloc(dwell*4,sizeof(*raw)); assert(template&&raw);
    for(size_t k=0;k<n;k++){template[k][0]=(float)((int)(k%23)-11);template[k][1]=(float)((int)(k%19)-9);}
    if(extreme)for(size_t k=0;k<dwell*4;k++)raw[k]=(k&1)?INT16_MIN:INT16_MAX;
    assert(!bank_init(&b,template,n,(double)rate));
    for(int m=0;m<3;m++)for(size_t k=0;k<n;k++){
        unsigned expected=0;
        for(int frame=0;frame<FRAMES;frame++)if(proposal_frame_selected(frame)){
            size_t off=(size_t)llround(frame*rate/750.0),available=off<count?count-off:0;
            size_t valid=available<n?available:n,lag=(size_t)lags[m];
            valid=available>lag?(valid<available-lag?valid:available-lag):0;
            if(k<valid)++expected;
        }
        assert(b.support[m][k]==expected);
    }
    fftwf_complex *out[3]={b.folded,b.folded_extra[0],b.folded_extra[1]};
    for(int m=0;m<3;m++)memset(out[m],0,n*sizeof(*out[m]));
    for(int frame=0;frame<FRAMES;frame++)if(proposal_frame_selected(frame)){
        size_t valid[3]={b.valid[0][frame],b.valid[1][frame],b.valid[2][frame]};
        fold_three(out,raw,0,b.frame_offset[frame],valid,1);
    }
    for(int m=0;m<3;m++)for(size_t k=0;k<n;k++){assert(isfinite(out[m][k][0]));assert(isfinite(out[m][k][1]));}
    bank_free(&b);fftwf_free(template);free(raw);
}
int main(void){size_t rates[]={2500000,5000000,7500000,10000000};for(size_t i=0;i<4;i++){run_rate(rates[i],0);run_rate(rates[i],1);}puts("proposal budget support exact: all rates, zero, extreme, selected-frame tails");return 0;}
