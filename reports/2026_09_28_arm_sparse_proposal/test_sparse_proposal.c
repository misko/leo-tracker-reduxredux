#include "full_search.c"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t state=0xa35179dbu;
static float random_float(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-23f-1)*.5f;}

static void trial(uint32_t rate,size_t count,int zero)
{
    size_t n=(rate+375)/750,cells=11*n;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control)),*samples=calloc(count,sizeof(*samples));
    double *proposal=malloc(cells*sizeof(*proposal));unsigned char *eligible=malloc(n);
    assert(exact&&control&&samples&&proposal&&eligible);
    for(size_t k=0;k<n;++k){exact[k].re=random_float();exact[k].im=random_float();control[k].re=random_float();control[k].im=random_float();}
    if(!zero)for(size_t k=0;k<count;++k){samples[k].re=random_float();samples[k].im=random_float();}
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w&&!ingest(w,samples,count));
    assert(!sparse_coarse(w,count,eligible));memcpy(proposal,w->grid,cells*sizeof(*proposal));
    assert(!coarse_fp32(w,count));
    size_t eligible_count=0;
    for(size_t e=0;e<n;++e)if(eligible[e]) {
        ++eligible_count;
        int first=e? -1:0,last=e+1<n?1:0;
        for(int d=first;d<=last;++d)for(int f=0;f<11;++f)
            assert(proposal[f*n+e+d]==w->grid[f*n+e+d]);
    }
    if(LEO_SPARSE_COARSE_FRAMES==16&&LEO_SPARSE_COARSE_SYMBOLS==12) {
        assert(eligible_count==n);
        assert(!memcmp(proposal,w->grid,cells*sizeof(*proposal)));
    } else if(zero) assert(eligible_count==n);
    else assert(eligible_count>0&&eligible_count<=3*LEO_SPARSE_CENTERS+2);
    free(eligible);free(proposal);leo_presence_destroy(w);free(samples);free(control);free(exact);
}

static void edge_trial(uint32_t rate,int endpoint)
{
    size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*samples=calloc(count,sizeof(*samples));
    unsigned char *eligible=malloc(n);assert(exact&&samples&&eligible);
    for(size_t k=0;k<n;++k){exact[k].re=cos(.017*k);exact[k].im=sin(.017*k);}
    leo_presence_workspace *w=leo_presence_create(rate,exact,exact,n);assert(w);
    int epoch=endpoint?(int)n-1:0;
    for(int si=0;si<LEO_SPARSE_COARSE_SYMBOLS;++si){int symbol=si*12/LEO_SPARSE_COARSE_SYMBOLS;
      int taps=(int)(w->stops[symbol]-w->starts[symbol]);
      for(int fi=0;fi<LEO_SPARSE_COARSE_FRAMES;++fi){int frame=fi*16/LEO_SPARSE_COARSE_FRAMES;
        ptrdiff_t base=w->starts[symbol]+w->offsets[frame]+epoch;
        if(base+taps>(ptrdiff_t)count)continue;
        for(int k=0;k<taps;++k){samples[base+k].re=(float)creal(w->exact[w->starts[symbol]+k]);samples[base+k].im=(float)cimag(w->exact[w->starts[symbol]+k]);}
      }}
    assert(!ingest(w,samples,count)&&!sparse_coarse(w,count,eligible));
    assert(eligible[epoch]);
    size_t capacity=11*n,np=0;leo_full_search_peak *peaks=malloc(capacity*sizeof(*peaks));assert(peaks);
    int endpoint_peak=0;
    for(int f=0;f<11;++f)for(int e=0;e<(int)n;++e)if(eligible[e]) {
        double v=w->grid[f*n+e],left=e?w->grid[f*n+e-1]:-INFINITY,right=e+1<(int)n?w->grid[f*n+e+1]:-INFINITY;
        if(v>=left&&v>=right&&(v>left||v>right)) {
            peaks[np++]=(leo_full_search_peak){v,e,f};if(e==epoch)endpoint_peak=1;
        }
    }
    assert(endpoint_peak);
    leo_full_search_peak retained[LEO_FULL_SEARCH_MAX_CANDIDATES];
    size_t nr=leo_full_search_retain_peaks(peaks,np,(int32_t)n,w->frequencies,retained);int found=0;
    for(size_t i=0;i<nr;++i)if(retained[i].epoch==epoch)found=1;
    assert(found);free(peaks);
    leo_presence_destroy(w);free(eligible);free(samples);free(exact);
}

int main(void)
{
    { unsigned char repaired[5]={1,1,0,1,1},eligible[5];sparse_set_eligible(eligible,repaired,5);
      assert(eligible[0]&&!eligible[1]&&!eligible[2]&&!eligible[3]&&eligible[4]); }
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;++r){size_t partial=(size_t)ceil(rates[r]/375.0);trial(rates[r],partial,0);trial(rates[r],rates[r]/50,0);trial(rates[r],rates[r]/50,1);edge_trial(rates[r],0);edge_trial(rates[r],1);}
    printf("sparse proposal passed frames=%d symbols=%d: all rates partial/full/zero, exact repairs\n",LEO_SPARSE_COARSE_FRAMES,LEO_SPARSE_COARSE_SYMBOLS);return 0;
}
