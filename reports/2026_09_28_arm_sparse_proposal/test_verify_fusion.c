#include "full_search.c"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t state=0x6a519d3bu;
static double random_value(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-23-1)*.5;}

static void trial(uint32_t rate,size_t count,int zero)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    assert(exact&&control);
    for(size_t k=0;k<n;++k){exact[k].re=random_value();exact[k].im=random_value();control[k].re=random_value();control[k].im=random_value();}
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);assert(w);
    for(size_t k=0;k<count;++k)w->samples[k]=zero?0:random_value()+I*random_value();
    const int epochs[]={0,(int)n/2,(int)n-1};
    const double cfos[]={-317321.25,0,283199.75};
    for(int q=0;q<3;++q) {
        double want[3]={
            normalized_score(w,count,epochs[q],cfos[q],w->exact,2),
            normalized_score(w,count,epochs[q],cfos[q],w->exact,3),
            normalized_score(w,count,epochs[q],cfos[q],w->control,3)};
        double got[3];full_verification_scores(w,count,epochs[q],cfos[q],got);
        for(int k=0;k<3;++k)if(got[k]!=want[k]) {
            fprintf(stderr,"rate=%u count=%zu zero=%d epoch=%d score=%d got=%.17g want=%.17g\n",rate,count,zero,epochs[q],k,got[k],want[k]);
            abort();
        }
    }
    leo_presence_destroy(w);free(control);free(exact);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;++r) {
        size_t minimum=(size_t)ceil(rates[r]/375.0),full=rates[r]/50;
        trial(rates[r],minimum,0);trial(rates[r],minimum+1,0);
        trial(rates[r],full,0);trial(rates[r],full,1);
    }
    puts("verification fusion exact parity passed: all rates, full/partial/zero");return 0;
}
