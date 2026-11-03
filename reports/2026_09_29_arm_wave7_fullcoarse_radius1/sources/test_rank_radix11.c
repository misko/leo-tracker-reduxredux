#define LEO_PROPOSAL_LIBRARY 1
#include "proposal_core.c"
#include <assert.h>

static int ascending_reference(const void *a,const void *b){
    const ranked *x=a,*y=b;
    if(x->score<y->score)return -1;
    if(x->score>y->score)return 1;
    return (x->index>y->index)-(x->index<y->index);
}
static void check_rank(float *values,size_t n){
    ranked *a=malloc(n*sizeof(*a)),*scratch=malloc(n*sizeof(*scratch)),*want=malloc(n*sizeof(*want));assert(a&&scratch&&want);
    for(size_t k=0;k<n;k++)a[k]=want[k]=(ranked){values[k],(int)k};
    qsort(want,n,sizeof(*want),ascending_reference);ranked *got=rank_radix(a,scratch,n);
    for(size_t k=0;k<n;k++){assert(got[k].score==want[k].score);assert(got[k].index==want[k].index);}
    free(a);free(scratch);free(want);
}
static void check_regions(void){
    enum { Z=128,N=100 };float s[Z]={0};ranked work[Z];int a[4],b[4];
    s[0]=7;s[3]=9;s[18]=9;s[31]=4;s[64]=8;s[127]=6;
    int na=top4_linear(s,Z,N,a,work),nb=top4_sort_reference(s,Z,N,b,work);assert(na==nb);for(int k=0;k<na;k++)assert(a[k]==b[k]);
    memset(s,0,sizeof(s));assert(top4_linear(s,Z,N,a,work)==0);assert(top4_sort_reference(s,Z,N,b,work)==0);
    s[4]=-0.0f;s[8]=0.0f;assert(top4_linear(s,Z,N,a,work)==0);
}
int main(void){
    enum { N=20000 };float *v=malloc(N*sizeof(*v));assert(v);
    uint32_t state=0x12345678u;for(int k=0;k<N;k++){state=1664525u*state+1013904223u;v[k]=(float)(int32_t)state/65536.0f;}check_rank(v,N);
    for(int k=0;k<N;k++)v[k]=(float)(k%17-8);
    v[0]=0.0f;v[1]=-0.0f;check_rank(v,N);
    for(int k=0;k<N;k++)v[k]=3.0f;
    check_rank(v,N);
    for(int k=0;k<N;k++)v[k]=(float)k;
    check_rank(v,N);
    for(int k=0;k<N;k++)v[k]=(float)(N-k);
    check_rank(v,N);
    check_regions();free(v);puts("rank radix 11/11/10: exact");return 0;
}
