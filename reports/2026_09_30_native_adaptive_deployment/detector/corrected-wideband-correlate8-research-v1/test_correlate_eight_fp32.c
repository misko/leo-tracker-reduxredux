#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "source/native/adaptive/detector/kernel/private/correlate_eight_fp32.h"

enum { CAPACITY=22, MAX_TAPS=45 };

static uint32_t state=0x4c454f38u;

static float sample_value(float scale)
{
    state=state*1664525u+1013904223u;
    int32_t value=(int32_t)(state>>8)-(int32_t)0x00800000;
    return (float)value*(scale/8388608.0f);
}

static void one_case(int taps,int frequencies)
{
    float samples[2*MAX_TAPS];
    float real[CAPACITY*MAX_TAPS],imag[CAPACITY*MAX_TAPS];
    float four_real[CAPACITY],four_imag[CAPACITY];
    float eight_real[CAPACITY],eight_imag[CAPACITY];
    for(int k=0;k<2*MAX_TAPS;++k)samples[k]=sample_value(1.0f);
    for(int k=0;k<CAPACITY*MAX_TAPS;++k){
        real[k]=sample_value(16.0f);imag[k]=sample_value(16.0f);
    }
    memset(four_real,0xa5,sizeof(four_real));
    memset(four_imag,0xa5,sizeof(four_imag));
    memcpy(eight_real,four_real,sizeof(eight_real));
    memcpy(eight_imag,four_imag,sizeof(eight_imag));
    leo_research_correlate_four_fp32(samples,real,imag,taps,frequencies,
        CAPACITY,four_real,four_imag);
    leo_research_correlate_eight_fp32(samples,real,imag,taps,frequencies,
        CAPACITY,eight_real,eight_imag);
    assert(memcmp(four_real,eight_real,sizeof(four_real))==0);
    assert(memcmp(four_imag,eight_imag,sizeof(four_imag))==0);
}

int main(void)
{
    size_t cases=0;
    for(int repeat=0;repeat<64;++repeat)
        for(int taps=1;taps<=MAX_TAPS;++taps)
            for(int frequencies=1;frequencies<=CAPACITY;++frequencies){
                one_case(taps,frequencies);++cases;
            }
    printf("correlate eight: %zu exact four-wide comparisons pass\n",cases);
    return 0;
}
