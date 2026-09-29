#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
typedef struct {float score;int index;} ranked;
#include "radix.h"
static int compare(const void *a,const void *b){const ranked *x=a,*y=b;if(x->score<y->score)return -1;if(x->score>y->score)return 1;return (x->index>y->index)-(x->index<y->index);}
int main(void){
    enum {N=20000}; ranked a[N],b[N],tmp[N];uint32_t rng=91237;
    for(int trial=0;trial<8;trial++){
        for(int k=0;k<N;k++){
            rng=rng*1664525u+1013904223u;
            float score=(float)((int)(rng%20001)-10000)/17;
            if(trial==1)score=0;
            if(trial==2)score=k%2?-0.0f:0.0f;
            if(trial==3)score=(float)k;
            if(trial==4)score=(float)(N-k);
            if(trial==5)score*=1e-38f;
            if(trial==6)score*=1e30f;
            a[k]=(ranked){score,k};b[k]=a[k];
        }
        qsort(b,N,sizeof(*b),compare);rank_radix(a,tmp,N);
        for(int k=0;k<N;k++){assert(a[k].score==b[k].score);assert(a[k].index==b[k].index);}
    }
    puts("radix ordering matches comparison sort, including ties and signed zero");return 0;
}
