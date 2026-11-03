static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t rng=7;
static float rv(void){rng=1664525*rng+1013904223;return (float)(int32_t)rng/2147483648.0f;}
static void trial(uint32_t rate,int active_count,int zero){
 size_t n=(rate+375)/750,count=rate/50;leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));assert(exact&&control);
 for(size_t k=0;k<n;++k){exact[k]=(leo_presence_complex){rv(),rv()};control[k]=(leo_presence_complex){rv(),rv()};}
 leo_presence_workspace *a=leo_presence_create(rate,exact,control,n),*b=leo_presence_create(rate,exact,control,n);assert(a&&b);
 for(size_t k=0;k<count;++k){float re=zero?0:rv(),im=zero?0:rv();a->float_samples[2*k]=b->float_samples[2*k]=re;a->float_samples[2*k+1]=b->float_samples[2*k+1]=im;a->prefix[k+1]=b->prefix[k+1]=a->prefix[k]+(double)re*re+(double)im*im;}
 regional_count=active_count;for(int i=0;i<active_count;++i)regional_epochs[i]=11+i;a->coarse_input_prepared=b->coarse_input_prepared=1;a->coarse_prepared_count=b->coarse_prepared_count=count;assert(!coarse_fp32(a,count));
 memset(b->float_accumulated,0,CFO_COUNT*b->n*sizeof(float));memset(b->support,0,b->n*sizeof(int32_t));
 for(int symbol=0;symbol<12;symbol+=LEO_PRESENCE_ANCHOR_STRIDE){int taps=(int)(b->stops[symbol]-b->starts[symbol]);for(int slot=0;slot<LEO_PRESENCE_COARSE_FRAMES;++slot){int frame=coarse_frame_index(slot);ptrdiff_t base=b->starts[symbol]+b->offsets[frame],valid=(ptrdiff_t)count-taps+1-base;if(valid<=0)break;if(valid>(ptrdiff_t)b->n)valid=b->n;for(int q=0;q<active_count;++q){int e=regional_epochs[q];if(e<valid)assert(!coarse_fp32_add(b,symbol,base+e,e));}}}
 float worst=0;for(int q=0;q<active_count;++q){int e=regional_epochs[q];assert(a->support[e]==b->support[e]);for(int f=0;f<12;++f)worst=fmaxf(worst,fabsf(a->float_accumulated[12*e+f]-b->float_accumulated[12*e+f]));}assert(worst<2e-4f);
 leo_presence_destroy(a);leo_presence_destroy(b);free(exact);free(control);
}
int main(void){const uint32_t rates[]={2500000,5000000,7500000,10000000};const int counts[]={5,11,22,33,44};for(int r=0;r<4;++r)for(int q=0;q<5;++q){trial(rates[r],counts[q],0);trial(rates[r],counts[q],1);}puts("integrated Winograd coarse passed all rates, zero/random, fifth epochs, and 11/22/33/44 supports");}
