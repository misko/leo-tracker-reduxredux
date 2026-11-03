#define LEO_PROPOSAL_LIBRARY 1
#define LEO_PROPOSAL_OMIT_POWER 1
#include "proposal_core.c"
#include <assert.h>

int main(void)
{
    const size_t rates[]={2500000,5000000,7500000,10000000};
    assert(lag_enabled(0)+lag_enabled(1)+lag_enabled(2)==1);
    for(size_t r=0;r<sizeof(rates)/sizeof(rates[0]);r++){
        size_t n=(rates[r]+375)/750,dwell=rates[r]*120/1000;
        double (*reference)[2]=calloc(n,sizeof(*reference));int16_t *raw=calloc(dwell*4,sizeof(*raw));
        int centers[4],count=-1;leo_proposal_timing timing={0};assert(reference&&raw);
        for(size_t k=0;k<n;k++)reference[k][0]=1.0;
        leo_proposal_workspace *w=leo_proposal_create(reference,n,rates[r]);assert(w);
        assert(!leo_proposal_top4(w,raw,0,0,centers,&count,&timing));assert(count==0);
        leo_proposal_destroy(w);free(raw);free(reference);
    }
    puts("single-lag resampled omit-power proposal passed feature-mask and all-rate zero-input checks");
    return 0;
}
