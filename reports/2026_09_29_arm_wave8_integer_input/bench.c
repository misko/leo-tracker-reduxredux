#define _GNU_SOURCE
#define leo_dwell_input_prepare original_prepare
#include "dwell_input.h"
#undef leo_dwell_input_prepare
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sched.h>

/* CI16 component squares fit int32; their sum requires unsigned 32 bits.
 * At <=10 MS/s and 120 ms the scaled cumulative integer is <2^52, so
 * replacing two double squares/adds by this exact integer sum changes no
 * prefix bit. This bound is part of the tested input contract. */
static int integer_prepare(leo_dwell_input *d,const int16_t *iq,size_t count)
{
    if (!d||!iq||!count||count>1200000) return -1;
    *d=(leo_dwell_input){.count=count};
    for(int rx=0;rx<2;++rx){
        d->raw[rx]=malloc(count*sizeof(*d->raw[rx]));
        d->normalized[rx]=malloc(2*count*sizeof(float));
        d->prefix[rx]=malloc((count+1)*sizeof(double));
        if(!d->raw[rx]||!d->normalized[rx]||!d->prefix[rx]){
            leo_dwell_input_free(d);return -1;
        }
        double sum=0;d->prefix[rx][0]=0;
        for(size_t k=0;k<count;++k){
            int32_t ir=iq[4*k+2*rx],ii=iq[4*k+2*rx+1];
            d->raw[rx][k]=(double)ir+I*(double)ii;
            d->normalized[rx][2*k]=(float)ir*(1.0f/32768.0f);
            d->normalized[rx][2*k+1]=(float)ii*(1.0f/32768.0f);
            uint32_t energy=(uint32_t)(ir*ir)+(uint32_t)(ii*ii);
            sum+=(double)energy*(1.0/1073741824.0);
            d->prefix[rx][k+1]=sum;
        }
    }
    return 0;
}
static double now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+1e-9*t.tv_nsec;}
int main(void){
#ifdef __arm__
    cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);assert(!sched_setaffinity(0,sizeof(set),&set));
#endif
    uint32_t state=7;volatile double sink=0;
    for(size_t rate=2500000;rate<=10000000;rate+=2500000){
        size_t n=rate*120/1000;int16_t *iq=malloc(4*n*sizeof(*iq));assert(iq);
        for(size_t k=0;k<4*n;++k){state=1664525u*state+1013904223u;iq[k]=(int16_t)(state>>16);}
        for(size_t k=0;k<128;++k)iq[k]=INT16_MIN;
        leo_dwell_input a,b;assert(!original_prepare(&a,iq,n));assert(!integer_prepare(&b,iq,n));
        for(int rx=0;rx<2;++rx){assert(!memcmp(a.raw[rx],b.raw[rx],n*sizeof(double complex)));assert(!memcmp(a.normalized[rx],b.normalized[rx],2*n*sizeof(float)));assert(!memcmp(a.prefix[rx],b.prefix[rx],(n+1)*sizeof(double)));}
        leo_dwell_input_free(&a);leo_dwell_input_free(&b);
        double times[2]={0};for(int rep=0;rep<6;++rep)for(int z=0;z<2;++z){int method=(rep+z)%2;double t=now();assert(!(method?integer_prepare(&a,iq,n):original_prepare(&a,iq,n)));times[method]+=now()-t;sink+=a.prefix[0][n];leo_dwell_input_free(&a);}
        printf("rate=%zu baseline_ms=%.6f integer_ms=%.6f exact=1\n",rate,1000*times[0]/6,1000*times[1]/6);free(iq);
    }
    assert(sink>0);return 0;
}
