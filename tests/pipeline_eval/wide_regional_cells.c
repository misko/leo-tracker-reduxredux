#include <assert.h>
#include <math.h>
#include <stdint.h>

#define CFO_COUNT 24
#define WIDE_REGIONAL_BINS 21
#include "wide_regional_cfo.h"

static uint32_t state=47;

static float next_sample(void)
{
    state=1664525u*state+1013904223u;
    return (float)((int)(state>>16)-32768)/32768.0f;
}

int main(void)
{
    for (int taps=1;taps<=45;++taps) {
        float samples[90],real[45*CFO_COUNT],imag[45*CFO_COUNT],actual[CFO_COUNT]={0};
        for (int k=0;k<taps;++k) {
            samples[2*k]=k%9 ? next_sample() : -1.0f;
            samples[2*k+1]=k%7 ? next_sample() : 32767/32768.0f;
            for (int f=0;f<CFO_COUNT;++f) {
                real[CFO_COUNT*k+f]=next_sample();
                imag[CFO_COUNT*k+f]=next_sample();
            }
        }
        wide_regional_float_add(samples,real,imag,taps,0.37f,actual);
        for (int f=0;f<WIDE_REGIONAL_BINS;++f) {
            float r=0,i=0;
            for (int k=0;k<taps;++k) {
                float rr=real[CFO_COUNT*k+f],ri=imag[CFO_COUNT*k+f];
                r+=samples[2*k]*rr+samples[2*k+1]*ri;
                i+=samples[2*k+1]*rr-samples[2*k]*ri;
            }
            assert(actual[f]==sqrtf(r*r+i*i)*0.37f);
        }
        for (int f=WIDE_REGIONAL_BINS;f<CFO_COUNT;++f) assert(actual[f]==0);
    }
    return 0;
}
