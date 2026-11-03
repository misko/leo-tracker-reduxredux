/* Private coarse-mask qualification: no detector/ranking assertions here. */
#include "full_search.c"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint32_t state=0x4d595df4u;
static double rnd(void) { state=1664525u*state+1013904223u; return (state>>8)*0x1p-23-.5; }

static void check_grid(const leo_presence_workspace *got,const double *reference,
    unsigned mask,int zero)
{
    for(int f=0;f<11;++f) for(size_t e=0;e<got->n;++e)
        if(zero || ((mask>>f)&1u)) assert(got->grid[f*got->n+e]==reference[f*got->n+e]);
        else assert(got->grid[f*got->n+e]==-INFINITY);
}

static void masked_cycle(leo_presence_workspace *w,size_t count,
    const double *reference,unsigned mask,int zero)
{
    assert(!leo_full_search_set_mask(mask));
    full_coarse_pack(w); assert(!coarse(w,count,NULL)); full_coarse_scatter(w);
    check_grid(w,reference,mask,zero);
}

static void trial(uint32_t rate,size_t count,int zero)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *x=calloc(count,sizeof(*x)),*a=calloc(n,sizeof(*a)),*b=calloc(n,sizeof(*b));
    assert(x&&a&&b);
    for(size_t i=0;i<n;++i) a[i]=(leo_presence_complex){rnd(),rnd()},b[i]=(leo_presence_complex){rnd(),rnd()};
    if(!zero) for(size_t i=0;i<count;++i)x[i]=(leo_presence_complex){rnd(),rnd()};
    leo_presence_workspace *oracle=leo_presence_create(rate,a,b,n),*w=leo_presence_create(rate,a,b,n);
    assert(oracle&&w&& !ingest(oracle,x,count) && !ingest(w,x,count));
    assert(!leo_full_search_set_mask(2047) && !coarse(oracle,count,NULL));
    double *reference=malloc(12*n*sizeof(*reference)); assert(reference); memcpy(reference,oracle->grid,12*n*sizeof(*reference));
    /* Reuse one workspace: mask -> full -> different noncontiguous mask. */
    masked_cycle(w,count,reference,0x155u,zero);
    assert(!leo_full_search_set_mask(2047) && !coarse(w,count,NULL));
    for(size_t i=0;i<12*n;++i) assert(w->grid[i]==reference[i]);
    masked_cycle(w,count,reference,0x2aau,zero);
    free(reference); leo_presence_destroy(w); leo_presence_destroy(oracle); free(b);free(a);free(x);
}

int main(int argc,char **argv)
{
    int smoke=argc==2 && !strcmp(argv[1],"--smoke2p5"); assert(argc==1||smoke);
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    assert(leo_full_search_set_mask(0)==-1 && leo_full_search_set_mask(2048)==-1);
    for(size_t r=0;r<(smoke?1:4);++r) {
        trial(rates[r],rates[r]/50,0);
        trial(rates[r],(size_t)ceil(rates[r]/375.0),0);
        trial(rates[r],rates[r]/50,1);
    }
    puts("coarse mask: same-workspace restoration, partial, zero, all rates pass");
    return 0;
}
