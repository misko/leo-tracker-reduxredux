#include "proposal_core.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void one_case(size_t rate,int pattern)
{
    size_t n=rate/750,dwell=rate*120/1000;
    double (*template)[2]=calloc(n,sizeof(*template));
    int16_t *raw=calloc(dwell*4,sizeof(*raw));
    assert(template&&raw);
    for(size_t k=0;k<n;k++) { template[k][0]=(double)((int)(k%31)-15); template[k][1]=(double)((int)(k%17)-8); }
    if(pattern) for(size_t k=0;k<dwell*4;k++) raw[k]=(k&1)?INT16_MIN:INT16_MAX;
    leo_proposal_workspace *w=leo_proposal_create((const double (*)[2])template,n,(double)rate);
    int first[4]={0},again[4]={0},count=0,repeat=0;
    assert(w);
    assert(!leo_proposal_top4(w,raw,0,1,first,&count,NULL));
    assert(!leo_proposal_top4(w,raw,0,1,again,&repeat,NULL));
    assert(count==repeat&&count>=0&&count<=4&&!memcmp(first,again,sizeof(first)));
    for(int i=0;i<count;i++)assert(first[i]>=0&&first[i]<(int)n);
    leo_proposal_destroy(w);free(raw);free(template);
}
int main(void)
{
    size_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t i=0;i<4;i++)for(int pattern=0;pattern<2;pattern++)one_case(rates[i],pattern);
    puts("proposal fastmath: all-rate zero, CI16-extreme, and inherited frame-tail cases");
    return 0;
}
