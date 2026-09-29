static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t rng=0x93d728b1u;
static double random_value(void)
{
    rng=1664525u*rng+1013904223u;
    return ((rng>>8)*0x1p-23-1)*.5;
}

static void run_rate(uint32_t rate, int partial)
{
    size_t n=(rate+375)/750;
    size_t count=partial ? (size_t)ceil(rate/375.0) : rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    leo_presence_complex *control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for(size_t k=0;k<n;++k) {
        exact[k]=(leo_presence_complex){random_value(),random_value()};
        control[k]=(leo_presence_complex){random_value(),random_value()};
    }
    for(size_t k=0;k<count;++k)
        samples[k]=(leo_presence_complex){random_value(),random_value()};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);
    assert(w&&!ingest(w,samples,count));
    w->acquisition_first_frame=0;

    const double starts[]={-400000.0,-240000.0,80000.0,240000.0};
    int epoch=partial ? 0 : (int)(n/3);
    leo_fine_reuse_cache cache;
    leo_fine_reuse_init(&cache,w->fine_fft.size);
    for(int q=0;q<4;++q) {
        int bins=q==0 ? 17 : 129;
        double *expected=calloc((size_t)bins,sizeof(double));
        double *actual=calloc((size_t)bins,sizeof(double));
        assert(expected&&actual);
        fine_scores(w,count,epoch,starts[q],bins,expected);
        assert(!leo_fine_reuse_scores(w,count,epoch,starts[q],bins,actual,&cache));
        assert(!memcmp(expected,actual,(size_t)bins*sizeof(double)));
        free(actual);free(expected);
    }
    assert(cache.transforms==1&&cache.hits==3&&cache.count==1);
    leo_fine_reuse_free(&cache);

    /* A fresh call owns fresh state: changed samples cannot observe the old
     * window's epoch entry. */
    if(count) samples[count/2].re+=0.125;
    assert(!ingest(w,samples,count));
    double expected[33],actual[33];
    fine_scores(w,count,epoch,-80000.0,33,expected);
    leo_fine_reuse_init(&cache,w->fine_fft.size);
    assert(!leo_fine_reuse_scores(w,count,epoch,-80000.0,33,actual,&cache));
    assert(!memcmp(expected,actual,sizeof(expected)));
    assert(cache.transforms==1&&cache.hits==0);
    leo_fine_reuse_free(&cache);
    leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int i=0;i<4;++i) { run_rate(rates[i],0);run_rate(rates[i],1); }
    puts("fine reuse passed: exact shared-epoch ranges, reset, partial frames, all rates");
    return 0;
}
