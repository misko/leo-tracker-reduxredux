#include "fft.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
void leo_fft_forward_range(leo_fft *,const double complex *,size_t,size_t,size_t);
int main(void)
{
    uint32_t state=270927;unsigned checks=0;
    for(int rate=1;rate<=4;++rate){
        size_t used=(size_t)nearbyint(rate*2500000.0/750.0),n=2;
        while(n<used)n*=2;
        leo_fft a,b;if(leo_fft_init(&a,n)||leo_fft_init(&b,n))return 2;
        double complex *full=calloc(n,sizeof(*full)),*small=calloc(used,sizeof(*small));
        if(!full||!small)return 2;
        for(size_t k=0;k<used;++k){
            state=state*1664525u+1013904223u;double re=(int16_t)(state>>16);
            state=state*1664525u+1013904223u;double im=(int16_t)(state>>16);
            full[k]=small[k]=re+I*im;
        }
        leo_fft_forward(&a,full);
        size_t starts[]={0,n/3,n-1},lengths[]={1,n/3,n};
        for(size_t s=0;s<3;++s)for(size_t z=0;z<3;++z){
            leo_fft_forward_range(&b,small,used,starts[s],lengths[z]);
            for(size_t k=0;k<lengths[z];++k){
                size_t bin=(starts[s]+k)%n;
                if(creal(a.output[bin])!=creal(b.output[bin]) ||
                   cimag(a.output[bin])!=cimag(b.output[bin]))return 1;
            }
            ++checks;
        }
        free(full);free(small);leo_fft_free(&a);leo_fft_free(&b);
    }
    printf("{\"fft_range_cases\":%u,\"exact_mismatches\":0}\n",checks);return 0;
}
