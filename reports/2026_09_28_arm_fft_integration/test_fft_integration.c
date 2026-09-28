#define _POSIX_C_SOURCE 200809L
#include "full_search.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t state=0x97153badu;
static float random_float(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-23f-1.0f)*0.5f;}

static int run(uint32_t rate,size_t count,int zero,int expect_fallback)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    if(!exact||!control||!samples)return 1;
    for(size_t k=0;k<n;++k){exact[k].re=random_float();exact[k].im=random_float();control[k].re=random_float();control[k].im=random_float();}
    if(!zero)for(size_t k=0;k<count;++k){samples[k].re=random_float();samples[k].im=random_float();}
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);if(!w)return 1;
    double error;int equal,repaired,fallback;
    int rc=leo_fft_coarse_qualify(w,samples,count,&error,&equal,&repaired,&fallback);
    printf("rate=%u count=%zu zero=%d error=%.9g equal=%d repaired=%d fallback=%d\n",rate,count,zero,error,equal,repaired,fallback);
    leo_presence_destroy(w);free(samples);free(control);free(exact);
    return rc||!equal||(expect_fallback>=0&&fallback!=expect_fallback);
}

static int dynamic_range(void)
{
    uint32_t rate=5000000;size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact)),*control=calloc(n,sizeof(*control)),*samples=calloc(count,sizeof(*samples));
    if(!exact||!control||!samples)return 1;
    for(size_t k=0;k<n;++k){exact[k].re=random_float();exact[k].im=random_float();control[k]=exact[k];}
    for(size_t k=0;k<count;++k){samples[k].re=1e-9f;samples[k].im=-1e-9f;}
    samples[100].re=1;samples[100].im=-0.75f;
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);double error;int equal,repaired,fallback;
    int rc=!w||leo_fft_coarse_qualify(w,samples,count,&error,&equal,&repaired,&fallback);
    printf("dynamic_range equal=%d fallback=%d\n",equal,fallback);
    leo_presence_destroy(w);free(samples);free(control);free(exact);return rc||!equal||fallback!=1;
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t k=0;k<4;++k) {
        if(run(rates[k],(size_t)ceil(rates[k]/375.0),0,-1))return 1;
        if(run(rates[k],(size_t)ceil(rates[k]/375.0)+45,0,-1))return 1;
        if(run(rates[k],rates[k]/50,0,-1))return 1;
        if(run(rates[k],rates[k]/50,1,-1))return 1;
    }
    if(dynamic_range())return 1;
    if(setenv("LEO_FFT_COARSE_FORCE_FALLBACK","1",1)||run(5000000,5000000/50,1,1))return 1;
    puts("fft coarse integration tests passed");return 0;
}
