#define LEO_PROPOSAL_LIBRARY 1
#include "proposal_core.c"
#include <assert.h>
#include <stdio.h>

static void check(float *score,size_t z,size_t n){ranked *work=calloc(z,sizeof(*work));int old[4],fast[4];assert(work);int a=top4_sort_reference(score,z,n,old,work),b=top4_linear(score,z,n,fast,work);assert(a==b);for(int i=0;i<a;i++)assert(old[i]==fast[i]);free(work);}
int main(void){
    const size_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t r=0;r<4;r++){size_t n=(rates[r]+375)/750,z=next_power2(n);float *s=calloc(z,sizeof(*s));assert(s);
        for(size_t k=0;k<z;k++)s[k]=1;
        check(s,z,n);memset(s,0,z*sizeof(*s));
        s[0]=10;s[z-1]=10;s[1]=9;s[z/2]=10;s[z/2+8]=9;s[z/2+16]=8;check(s,z,n);
        memset(s,0,z*sizeof(*s));for(size_t k=0;k<z;k+=17)s[k]=(float)(k%5);check(s,z,n);free(s);}
    puts("rank fast passed all-rate flat, equal-tie, wrap and circular-separation equivalence");return 0;
}
