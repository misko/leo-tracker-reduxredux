static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x734ac91du;
static double random_value(void) {rng=1664525u*rng+1013904223u;return ((rng>>8)*0x1p-23-1)*.5;}

static void test_guard_classifier(void)
{
    double tied[]={.2,.4,.4,.1};
    assert(leo_fine_precision_guard(tied,-200.,100.,4)&LEO_FINE_GUARD_NEAR_TIE);
    double flat[]={.1,.4,.400001,.399999,.1};
    assert(leo_fine_precision_guard(flat,-200.,100.,5)&LEO_FINE_GUARD_INTERPOLATION);
    double invalid[]={.1,NAN,.2};
    assert(leo_fine_precision_guard(invalid,-100.,100.,3)&LEO_FINE_GUARD_NONFINITE);
    double clear[]={.1,.2,.8,.1,.05};
    assert(!leo_fine_precision_guard(clear,-200.,100.,5));
}

static void run_rate(uint32_t rate,int partial)
{
    size_t n=(rate+375)/750,count=partial?(size_t)ceil(rate/375.0):rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for(size_t k=0;k<n;++k){exact[k]=(leo_presence_complex){random_value(),random_value()};control[k]=(leo_presence_complex){random_value(),random_value()};}
    for(size_t k=0;k<count;++k)samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));
    w->acquisition_first_frame=0;
    int epoch=partial?0:(int)n/3,bins=129; double fp64[129],candidate[129];
    fine_scores(w,count,epoch,-240000.0,bins,fp64);
    leo_fine_precision_cache cache;assert(!leo_fine_precision_init(&cache,w->fine_fft.size));
    assert(!leo_fine_precision_scores(w,count,epoch,-240000.0,bins,candidate,&cache));
    assert(cache.count==1&&cache.transforms==1&&cache.calls==1);
#if LEO_FINE_PRECISION_GUARDED
    if(cache.fallbacks) assert(!memcmp(fp64,candidate,sizeof(fp64)));
    else for(int k=0;k<bins;++k) assert(isfinite(candidate[k]));
#else
    for(int k=0;k<bins;++k) {
        assert(isfinite(candidate[k]));
        assert(fabs(candidate[k]-fp64[k])<=2e-5*fmax(1.0,fabs(fp64[k])));
    }
#endif
    assert(!leo_fine_precision_scores(w,count,epoch,80000.0,33,candidate,&cache));
    assert(cache.count==1&&cache.transforms==1&&cache.hits==1&&cache.calls==2);
    leo_fine_precision_free(&cache);leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    test_guard_classifier();
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int i=0;i<4;++i){run_rate(rates[i],0);run_rate(rates[i],1);}
    puts("fine precision passed: FP32 spectra, guard classifier, cache, partial frames, all rates");
    return 0;
}
