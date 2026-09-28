#include "full_search.c"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t state=0x62cb9975u;
static double random_value(void)
{
    state=1664525u*state+1013904223u;
    return ((state>>8)*0x1p-23-1)*.5;
}

static void trial(uint32_t rate,size_t count,int zero)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    leo_presence_complex *control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for(size_t k=0;k<n;++k) {
        exact[k]=(leo_presence_complex){random_value(),random_value()};
        control[k]=(leo_presence_complex){random_value(),random_value()};
    }
    if(!zero) for(size_t k=0;k<count;++k)
        samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);
    leo_presence_workspace *oracle=leo_presence_create(rate,exact,control,n);
    assert(w&&oracle);
    leo_full_search_result result;
    assert(!leo_full_search_run(w,samples,count,&result));
    assert(result.fine_fft_cpu_ms==0&&result.conditioned_cpu_ms==0&&
        result.verification_cpu_ms==0&&result.conditioned_bins_screened==0&&
        result.conditioned_bins_rechecked==0);
    for(int i=0;i<result.candidate_count;++i) {
        leo_full_search_candidate *got=&result.candidates[i];
        double expected[3];
        assert(got->refinement_skipped&&got->glrt_complete);
        assert(got->candidate.acquired_cfo_hz==got->coarse_cfo_hz);
        assert(!leo_presence_glrt(oracle,samples,count,got->refined_epoch,
            got->coarse_cfo_hz,0,expected));
        assert(got->candidate.exact_score==expected[0]);
        assert(got->candidate.control_score==expected[1]);
        assert(got->candidate.tracking_cfo_hz==got->coarse_cfo_hz+expected[2]);
        assert(got->candidate.margin==expected[0]-expected[1]);
    }
    leo_presence_destroy(oracle);leo_presence_destroy(w);
    free(samples);free(control);free(exact);
}

int main(void)
{
#if !LEO_FULL_DIRECT_GLRT
#error "test_direct_glrt requires LEO_FULL_DIRECT_GLRT=1"
#endif
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;++r) {
        size_t partial=(size_t)ceil(rates[r]/375.0),full=rates[r]/50;
        trial(rates[r],partial,0);trial(rates[r],full,0);trial(rates[r],full,1);
    }
    puts("direct GLRT passed: all rates, partial/full/zero, direct API equality");
    return 0;
}
