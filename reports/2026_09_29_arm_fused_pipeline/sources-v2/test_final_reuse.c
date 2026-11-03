static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x83a19b47u;
static double random_value(void){rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-23-1)*.25;}

static void test_rate(uint32_t rate)
{
    size_t n=(rate+375)/750,count=3*n;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));assert(exact&&control&&samples);
    for(size_t k=0;k<n;++k){exact[k]=(leo_presence_complex){random_value(),random_value()};control[k]=(leo_presence_complex){random_value(),random_value()};}
    for(size_t k=0;k<count;++k)samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));
    w->acquisition_first_frame=0;

    final_glrt_cache glrt_cache={0};leo_full_search_result counters={0};
    double first[3],hit[3],nearby[3],shorter[3];const double cfo=12345.25;
    assert(!final_cached_glrt(&glrt_cache,w,count,0,cfo,first,&counters));
    assert(counters.actual_executed_glrt_calls==1&&counters.glrt_cache_hits==0);
    assert(!final_cached_glrt(&glrt_cache,w,count,0,cfo,hit,&counters));
    assert(!memcmp(first,hit,sizeof(first)));
    assert(counters.actual_executed_glrt_calls==1&&counters.glrt_cache_hits==1);
    assert(!final_cached_glrt(&glrt_cache,w,count,0,nextafter(cfo,INFINITY),nearby,&counters));
    assert(counters.actual_executed_glrt_calls==2&&counters.glrt_cache_hits==1);
    assert(!final_cached_glrt(&glrt_cache,w,count-1,0,cfo,shorter,&counters));
    assert(counters.actual_executed_glrt_calls==3);
    final_glrt_cache next_window={0};leo_full_search_result reset={0};
    assert(!final_cached_glrt(&next_window,w,count,0,cfo,hit,&reset));
    assert(reset.actual_executed_glrt_calls==1&&reset.glrt_cache_hits==0);
    assert(!memcmp(first,hit,sizeof(first)));

    final_conditioned_cache conditioned={0};leo_full_search_result logical={0};
    double winner,score,hit_winner,hit_score,near_winner,near_score;
    boundary_conditioned(w,count,0,cfo,&winner,&score,&reset);
    int expected_screened=reset.conditioned_bins_screened;
    int expected_rechecked=reset.conditioned_bins_rechecked;
    logical=(leo_full_search_result){0};
    final_cached_boundary(&conditioned,w,count,0,cfo,&hit_winner,&hit_score,&logical);
    assert(final_cfo_bits(winner)==final_cfo_bits(hit_winner));
    assert(final_cfo_bits(score)==final_cfo_bits(hit_score));
    assert(logical.conditioned_cache_hits==0);
    assert(logical.conditioned_bins_screened==expected_screened);
    assert(logical.conditioned_bins_rechecked==expected_rechecked);
    final_cached_boundary(&conditioned,w,count,0,cfo,&hit_winner,&hit_score,&logical);
    assert(final_cfo_bits(winner)==final_cfo_bits(hit_winner));
    assert(final_cfo_bits(score)==final_cfo_bits(hit_score));
    assert(logical.conditioned_cache_hits==1);
    assert(logical.conditioned_bins_screened==2*expected_screened);
    assert(logical.conditioned_bins_rechecked==2*expected_rechecked);
    final_cached_boundary(&conditioned,w,count,0,nextafter(cfo,INFINITY),&near_winner,&near_score,&logical);
    assert(logical.conditioned_cache_hits==1&&conditioned.count==2);
    final_conditioned_cache next_rx={0};leo_full_search_result reset_conditioned={0};
    final_cached_boundary(&next_rx,w,count,0,cfo,&hit_winner,&hit_score,&reset_conditioned);
    assert(reset_conditioned.conditioned_cache_hits==0&&next_rx.count==1);
    assert(final_cfo_bits(winner)==final_cfo_bits(hit_winner));
    assert(final_cfo_bits(score)==final_cfo_bits(hit_score));

    leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;++k)test_rate(rates[k]);
    puts("final reuse passed: exact hits, distinct adjacent CFO/count keys, logical counters, window/RX reset, all rates");
    return 0;
}
