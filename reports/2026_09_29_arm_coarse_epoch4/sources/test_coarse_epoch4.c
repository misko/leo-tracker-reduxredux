static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static int coarse_scalar_sparse(leo_presence_workspace *w,size_t count)
{
    const double scale=32768.0;
    memset(w->float_accumulated,0,CFO_COUNT*w->n*sizeof(float));
    memset(w->support,0,w->n*sizeof(int32_t));
    w->prefix[0]=0;
    for(size_t k=0;k<count;k++) {
        double re=creal(w->samples[k])/scale,im=cimag(w->samples[k])/scale;
        w->float_samples[2*k]=(float)re;w->float_samples[2*k+1]=(float)im;
        w->prefix[k+1]=w->prefix[k]+re*re+im*im;
    }
    for(int symbol=0;symbol<12;symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        int local=(int)w->starts[symbol],taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for(int slot=0;slot<LEO_PRESENCE_COARSE_FRAMES;slot++) {
            int frame=coarse_frame_index(slot);ptrdiff_t base=local+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-taps+1-base;
            if(valid<=0)break;
            if(valid>(ptrdiff_t)w->n)valid=(ptrdiff_t)w->n;
            for(int active=0;active<regional_count;active++) {
                ptrdiff_t epoch=regional_epochs[active];if(epoch>=valid)continue;
                if(coarse_fp32_add(w,symbol,base+epoch,epoch))return -1;
            }
        }
    }
    for(int f=0;f<CFO_COUNT;f++)for(size_t epoch=0;epoch<w->n;epoch++)
        w->grid[f*w->n+epoch]=w->support[epoch]>0?
            (double)w->float_accumulated[12*epoch+f]/w->support[epoch]:-INFINITY;
    return 0;
}

static void trial(uint32_t rate,size_t count,int mode)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for(size_t k=0;k<n;k++) {
        double a=.013*(double)k;exact[k]=(leo_presence_complex){cos(a),sin(a)};
    }
    if(mode)for(size_t k=0;k<count;k++) {
        int16_t re=(k&1)?INT16_MAX:INT16_MIN;
        int16_t im=(k%3)?(int16_t)(k*40503u):(int16_t)INT16_MIN;
        samples[k]=(leo_presence_complex){re,im};
    }
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w);
    assert(!ingest(w,samples,count));
    int candidate[]={0,1,2,3,10,20,21,22,23,(int)n-1};regional_count=0;
    for(size_t k=0;k<sizeof(candidate)/sizeof(candidate[0]);k++)
        if(candidate[k]>=0&&candidate[k]<(int)n&&(!regional_count||candidate[k]>regional_epochs[regional_count-1]))
            regional_epochs[regional_count++]=candidate[k];
    double *grid=malloc(CFO_COUNT*n*sizeof(*grid));int32_t *support=malloc(n*sizeof(*support));
    assert(grid&&support&&!coarse_scalar_sparse(w,count));
    memcpy(grid,w->grid,CFO_COUNT*n*sizeof(*grid));memcpy(support,w->support,n*sizeof(*support));
    assert(!coarse_fp32(w,count));
    assert(!memcmp(grid,w->grid,CFO_COUNT*n*sizeof(*grid)));
    assert(!memcmp(support,w->support,n*sizeof(*support)));
    free(support);free(grid);leo_presence_destroy(w);free(samples);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int k=0;k<4;k++) {
        trial(rates[k],(size_t)ceil(rates[k]/375.0),0);
        trial(rates[k],(size_t)ceil(rates[k]/375.0),1);
        trial(rates[k],rates[k]/50,1);
    }
    puts("coarse epoch4 exact parity: all rates zero/extreme partial/full sparse-four and scalar tails");
    return 0;
}
