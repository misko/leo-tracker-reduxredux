#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define LEO_PRESENCE_DIFFERENTIAL_LAG 4
typedef struct {
    size_t n;double rate;
    double *power_native_folded;
    double complex *diff_folded;
    int32_t *support,*diff_support;
} leo_presence_workspace;
static int frame_start(const leo_presence_workspace *w,int epoch,int frame)
{return epoch+(int)nearbyint(frame*(w->rate/750.0));}
#include "ci16_fold.h"
#include "coarse_fold_v2.h"
#include "ci16_energy_v2.h"

static leo_presence_workspace workspace(double rate,size_t n)
{
    leo_presence_workspace w={.rate=rate,.n=n};
    w.power_native_folded=calloc(n,sizeof(double));
    w.diff_folded=calloc(n,sizeof(double complex));
    w.support=calloc(n,sizeof(int32_t));w.diff_support=calloc(n,sizeof(int32_t));
    if(!w.power_native_folded||!w.diff_folded||!w.support||!w.diff_support)abort();
    return w;
}
static void release(leo_presence_workspace *w)
{free(w->power_native_folded);free(w->diff_folded);free(w->support);free(w->diff_support);}
int main(void)
{
#ifndef __ARM_NEON
    fprintf(stderr,"This qualification must execute the ARM NEON path.\n");return 2;
#endif
    unsigned checked=0;uint32_t state=190271;
    for(int r=1;r<=4;++r) {
        double rate=r*2500000.0;size_t n=(size_t)nearbyint(rate/750.0);
        leo_presence_workspace a=workspace(rate,n),b=workspace(rate,n);
        size_t lengths[]={0,1,4,7,n-1,n,n+3,2*n-1,2*n+7,(size_t)(rate/50)-5,(size_t)(rate/50)};
        for(size_t c=0;c<sizeof(lengths)/sizeof(*lengths);++c)for(int pattern=0;pattern<5;++pattern){
            size_t count=lengths[c];int16_t *iq=calloc(2*(count+1),sizeof(int16_t));if(!iq)abort();
            for(size_t k=0;k<2*count;++k){
                state=state*1664525u+1013904223u;
                iq[k]=pattern==0 ? INT16_MIN : pattern==1 ? INT16_MAX :
                    pattern==2 ? (k&1?INT16_MAX:INT16_MIN) :
                    pattern==3 ? ((k/7)&1?INT16_MIN:INT16_MAX) : (int16_t)(state>>16);
            }
            coarse_fold_ci16(&a,iq,count);opt_coarse_fold_ci16(&b,iq,count);
            double energy=0;
            for(size_t k=0;k<count;++k) {
                double re=iq[2*k],im=iq[2*k+1];energy+=re*re+im*im;
            }
            if(energy!=opt_ci16_energy(iq,count)) {
                fprintf(stderr,"energy mismatch\n");return 1;
            }
            if(memcmp(a.power_native_folded,b.power_native_folded,n*sizeof(double)) ||
               memcmp(a.diff_folded,b.diff_folded,n*sizeof(double complex)) ||
               memcmp(a.support,b.support,n*sizeof(int32_t)) ||
               memcmp(a.diff_support,b.diff_support,n*sizeof(int32_t))){
                fprintf(stderr,"mismatch rate=%.0f count=%zu pattern=%d\n",rate,count,pattern);return 1;
            }
            ++checked;free(iq);
        }
        release(&a);release(&b);
    }
    printf("{\"arm_neon_cases\":%u,\"energy_cases\":%u,\"exact_mismatches\":0}\n",checked,checked);return 0;
}
