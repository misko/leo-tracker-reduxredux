#define _POSIX_C_SOURCE 200809L
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

int main(void)
{
    const uint32_t rate=2500000;
    const size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    leo_presence_complex *control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for (size_t k=0;k<count;++k) samples[k].re=1;
    /* Alternating zero/nonzero template cells inside every selected symbol
     * make data support strictly larger than nonzero template support. */
    for (size_t k=0;k<n;++k) if (k&1) exact[k].re=1;
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n); assert(w);
    assert(!ingest(w,samples,count));
    memset(w->base,0,n*sizeof(*w->base));
    double template_energy=0;
    size_t supported=0,nonzero=0;
    for (int symbol=2;symbol<302;symbol+=2) {
        int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
        for (int k=begin;k<end;++k) {
            ++supported;
            template_energy+=power(w->exact[k]);
            w->base[k]=conj(w->exact[k]);
            nonzero+=w->exact[k]!=0;
        }
    }
    double score=fine_exact_bin(w,count,0,0,template_energy);
    double expected=(double)nonzero/sqrt(template_energy*supported);
    assert(fabs(score-expected)<1e-14);
    assert(score<0.8); /* the prior nonzero-only normalizer returned 1 */
    leo_presence_destroy(w);free(samples);free(control);free(exact);
    puts("fine screen zero-template support test passed");
    return 0;
}
