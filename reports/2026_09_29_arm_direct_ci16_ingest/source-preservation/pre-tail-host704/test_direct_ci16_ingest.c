static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void run_rate(uint32_t rate)
{
    size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *normalized=calloc(count,sizeof(*normalized));
    int16_t *packed=calloc(count*2,sizeof(*packed)),*dual=calloc(count*4,sizeof(*dual));
    assert(exact&&control&&normalized&&packed&&dual);
    for(size_t k=0;k<n;k++) {
        exact[k]=(leo_presence_complex){((int)(k%13)-6)/8.0,((int)(k%11)-5)/8.0};
        control[k]=(leo_presence_complex){exact[k].im,-exact[k].re};
    }
    for(size_t k=0;k<count;k++) {
        int16_t re=(int16_t)((k*7919u+17u)&65535u),im=(int16_t)((k*3571u+32768u)&65535u);
        if(k==0){re=INT16_MIN;im=INT16_MAX;}if(k+1==count){re=INT16_MAX;im=INT16_MIN;}
        packed[2*k]=re;packed[2*k+1]=im;dual[4*k]=123;dual[4*k+1]=-456;dual[4*k+2]=re;dual[4*k+3]=im;
        normalized[k]=(leo_presence_complex){ldexp((double)re,-15),ldexp((double)im,-15)};
    }
    leo_presence_workspace *a=leo_presence_create(rate,exact,control,n),*b=leo_presence_create(rate,exact,control,n);
    assert(a&&b);regional_count=0;for(size_t k=0;k<n;k++)regional_epochs[regional_count++]=(int)k;
    leo_full_search_result old_result,new_result;
    assert(!leo_full_search_run(a,normalized,count,&old_result));
    assert(!leo_full_search_run_ci16(b,dual+2,4,count,&new_result));
    assert(old_result.candidate_count==new_result.candidate_count);
    assert(old_result.retained_peak_count==new_result.retained_peak_count);
    assert(old_result.coarse_gate_skipped_count==new_result.coarse_gate_skipped_count);
    assert(!memcmp(old_result.candidates,new_result.candidates,sizeof(old_result.candidates)));
    for(size_t k=0;k<count;k++)assert(creal(b->samples[k])==normalized[k].re&&cimag(b->samples[k])==normalized[k].im);
    assert(leo_full_search_run_ci16(b,packed,1,count,&new_result)==-1);
    assert(leo_full_search_run_ci16(b,NULL,2,count,&new_result)==-1);
    assert(leo_full_search_run_ci16(b,packed,2,(size_t)ceil(rate/375.0)-1,&new_result)==-1);
    assert(leo_full_search_run_ci16(b,packed,2,b->max_samples+1,&new_result)==-1);
    leo_presence_destroy(b);leo_presence_destroy(a);free(dual);free(packed);free(normalized);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t k=0;k<4;k++)run_rate(rates[k]);
    puts("direct CI16 ingest passed all rates, stride2/4 view, tails, extremes, bounds, and exact candidates");
    return 0;
}
