#include <assert.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct {float score;int index;} ranked;

static size_t map_fft_index(size_t k,size_t n,size_t fft_n)
{
    return (k*n+fft_n/2)/fft_n%n;
}

static int ascending(const void *left,const void *right)
{
    const ranked *a=left,*b=right;
    if(a->score!=b->score)return a->score<b->score?-1:1;
    return (a->index>b->index)-(a->index<b->index);
}

static ranked *rank_radix(ranked *input,ranked *scratch,size_t count)
{
    (void)scratch;
    qsort(input,count,sizeof(*input),ascending);
    return input;
}

#include "scout_budget_centers.h"

static int original_next(const float *s,size_t z,size_t n,int *picked,int used)
{
    int peak=-1;
    for(size_t k=0;k<z;++k){
        float x=s[k],l=s[(k+z-1)%z],r=s[(k+1)%z];
        if(x<=0||x<l||x<r||(x==l&&x==r)||(peak>=0&&x<=s[peak]))continue;
        int p=(int)map_fft_index(k,n,z),overlap=0;
        for(int q=0;q<used;++q){
            int distance=abs(p-picked[q]);
            if(distance<5||(int)n-distance<5){overlap=1;break;}
        }
        if(!overlap)peak=(int)k;
    }
    return peak<0?-1:(int)map_fft_index((size_t)peak,n,z);
}

int main(void)
{
    const size_t bins=512,epochs=833;
    float score[bins];ranked work[bins],scratch[bins];int trial[16];
    uint32_t state=917;
    for(int test=0;test<1000;++test){
        for(size_t k=0;k<bins;++k){
            state=1664525u*state+1013904223u;
            score[k]=test<3?(float)test:(float)((state>>16)%12);
        }
        if(test==2){score[0]=3;score[bins-2]=3;score[bins/2]=3;}
        int count=scout_budget_centers(score,bins,epochs,trial,work,scratch);
        assert(count>=0&&count<=16);
        for(int j=0;j<count;++j)assert(original_next(score,bins,epochs,trial,j)==trial[j]);
        if(count<16)assert(original_next(score,bins,epochs,trial,count)==-1);
        if(test<2)assert(count==0);
        if(test==2)assert(count==2&&trial[0]==0);
    }
    return 0;
}
