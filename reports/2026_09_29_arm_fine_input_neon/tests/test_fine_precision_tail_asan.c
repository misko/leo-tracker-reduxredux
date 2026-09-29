/*
 * Dedicated regression reproducer for the prepared-FP32 input tail.
 *
 * `last` validates only the final active fine symbol.  The optimized loop
 * reads w->n samples, including the zero-template tail, so choose the final
 * epoch accepted by that former predicate and let ASan check the load.
 */
static int regional_count;
static int regional_epochs[13334];
#include "../sources/full_search.c"

#include <assert.h>
#include <stdio.h>

static void run_rate(uint32_t rate)
{
    const size_t n=(size_t)nearbyint(rate/750.0);
    const size_t count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    leo_presence_complex *control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact && control && samples);
    for (size_t k=0;k<n;++k) exact[k]=(leo_presence_complex){1.0,0.0};
    for (size_t k=0;k<count;++k) samples[k]=(leo_presence_complex){1.0,0.0};

    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);
    assert(w && !ingest(w,samples,count));
    assert(!coarse(w,count,NULL));
    w->acquisition_first_frame=0;

    const size_t last=(size_t)symbol_start(w,301)-1;
    const int epoch=(int)(count-last-1); /* accepted: epoch + last < count */
    assert((size_t)epoch+last<count);
    assert((size_t)epoch+w->n>count); /* but the prepared loop reads w->n */

    leo_fine_precision_cache cache;
    double scores[3];
    assert(!leo_fine_precision_init(&cache,w->fine_fft.size));
    (void)leo_fine_precision_scores(w,count,epoch,-1000.0,3,scores,&cache);
    leo_fine_precision_free(&cache);
    leo_presence_destroy(w);
    free(samples); free(control); free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for (size_t i=0;i<sizeof(rates)/sizeof(rates[0]);++i) run_rate(rates[i]);
    puts("unexpected: prepared-input tail remained in bounds");
    return 0;
}
