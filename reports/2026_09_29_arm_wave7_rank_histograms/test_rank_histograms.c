#define LEO_PROPOSAL_LIBRARY 1
#include "proposal_core.c"
#include <assert.h>
static void check(const float *v,size_t n){
    ranked *a=malloc(n*sizeof(*a)),*b=malloc(n*sizeof(*b));
    ranked *sa=malloc(n*sizeof(*sa)),*sb=malloc(n*sizeof(*sb));
    assert(a&&b&&sa&&sb);
    for(size_t k=0;k<n;k++)a[k]=b[k]=(ranked){v[k],(int)k};
    ranked *actual=rank_radix(a,sa,n),*expected=rank_radix_reference(b,sb,n);
    assert(!memcmp(actual,expected,n*sizeof(*actual)));
    free(a);free(b);free(sa);free(sb);
}
int main(void){
    enum{N=20000};float *v=malloc(N*sizeof(*v));assert(v);uint32_t random=71;
    for(int k=0;k<N;k++){
        random=1664525u*random+1013904223u;
        uint32_t bits=random;if((bits&0x7f800000u)==0x7f800000u)bits^=0x00800000u;
        memcpy(v+k,&bits,sizeof(bits));
    }
    check(v,N);
    for(int k=0;k<N;k++)v[k]=(float)(k%17-8);
    v[0]=0.0f;v[1]=-0.0f;check(v,N);
    for(int k=0;k<N;k++)v[k]=1.0f;
    check(v,N);
    for(int k=0;k<N;k++)v[k]=(float)(N-k);
    check(v,N);check(v,1);check(v,4096);check(v,8192);check(v,16384);
    free(v);puts("one-scan histogram rank exact across finite bit patterns, ties, zeros, flat and all grid sizes");return 0;
}
