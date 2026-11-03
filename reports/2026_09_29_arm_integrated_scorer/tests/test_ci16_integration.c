static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x913de751u;
static int16_t sample(void){rng=1664525u*rng+1013904223u;return (int16_t)(rng>>17);}
static double unit(void){rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-24-.5);}

static void run_rate(uint32_t rate)
{
    size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *fp=calloc(count,sizeof(*fp)); int16_t *iq=calloc(4*count,sizeof(*iq));
    assert(exact&&control&&fp&&iq);
    for(size_t k=0;k<n;++k){exact[k]=(leo_presence_complex){unit(),unit()};control[k]=(leo_presence_complex){unit(),unit()};}
    for(size_t k=0;k<count;++k){iq[4*k]=sample();iq[4*k+1]=sample();fp[k]=(leo_presence_complex){iq[4*k],iq[4*k+1]};}
    leo_presence_workspace *a=leo_presence_create(rate,exact,control,n),*b=leo_presence_create(rate,exact,control,n);assert(a&&b);
    leo_full_search_result reference,candidate;
    assert(!leo_full_search_run(a,fp,count,&reference));
    assert(!leo_full_search_run_ci16(b,iq,4,count,&candidate));
    assert(reference.candidate_count==candidate.candidate_count);
    assert(reference.retained_peak_count==candidate.retained_peak_count);
    assert(!memcmp(reference.candidates,candidate.candidates,sizeof(reference.candidates)));
    assert(reference.conditioned_fallback_count==candidate.conditioned_fallback_count);
    leo_presence_destroy(a);leo_presence_destroy(b);free(iq);free(fp);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int i=0;i<4;++i)run_rate(rates[i]);
    puts("integrated CI16 scorer passed: identical candidates and scores at all rates");
}
