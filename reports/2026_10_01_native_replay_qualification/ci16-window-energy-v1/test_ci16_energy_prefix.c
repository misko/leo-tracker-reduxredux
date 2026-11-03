#include "kernel/private/ci16_energy_prefix.h"
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    const size_t n=65536;
    double *prefix=malloc((n+1)*sizeof(*prefix));
    int16_t *iq=malloc(2*n*sizeof(*iq));assert(prefix&&iq);
    for(size_t k=0;k<n;++k) {
        iq[2*k]=(int16_t)((int)k-32768);
        iq[2*k+1]=(int16_t)((int)((k*173u)%65536)-32768);
    }
    for(int extremes=0;extremes<2;++extremes) {
        if(extremes)for(size_t k=0;k<2*n;++k)iq[k]=INT16_MIN;
        for(int near_limit=0;near_limit<2;++near_limit) {
            /* Emulate preceding full-scale CI16 samples near the proof limit. */
            prefix[0]=near_limit?2.0*(LEO_CI16_EXACT_PREFIX_MAX_SAMPLES-n):0;
            for(size_t k=0;k<n;++k) {
                double re=iq[2*k]/32768.0,im=iq[2*k+1]/32768.0;
                prefix[k+1]=prefix[k]+re*re+im*im;
            }
            for(size_t begin=0;begin<n;begin+=127) {
                size_t count=(begin*37)%3001;
                if(count>n-begin)count=n-begin;
                double expected=0;
                for(size_t k=begin;k<begin+count;++k) {
                    double re=iq[2*k],im=iq[2*k+1];
                    expected+=re*re+im*im;
                }
                double actual=leo_ci16_window_energy(prefix,begin,count);
                assert(!memcmp(&expected,&actual,sizeof(actual)));
                actual=leo_ci16_window_energy(prefix+begin,0,count);
                assert(!memcmp(&expected,&actual,sizeof(actual)));
            }
        }
    }
    free(iq);free(prefix);return 0;
}
