#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#include "stock_coarse.h"
#include "coarse_glrt_triplet.h"

static uint32_t state=4837163;

static float next_value(uint32_t modulus)
{
    state=1664525u*state+1013904223u;
    return (float)((int)(state%modulus)-(int)(modulus/2))/32768.0f;
}

int main(void)
{
    for (int taps=1;taps<=45;++taps) {
        for (int trial=0;trial<30;++trial) {
            float samples[2*47],real[12*45],imag[12*45];
            float original[36],candidate[36],inv[3];
            for (int k=0;k<94;++k) samples[k]=next_value(trial%2 ? 65536 : 51);
            for (int k=0;k<12*taps;++k) {
                real[k]=next_value(65536);
                imag[k]=next_value(65536);
            }
            for (int j=0;j<3;++j) inv[j]=0.5f+next_value(32768);
            for (int k=0;k<36;++k) original[k]=candidate[k]=0.5f+next_value(32768);
            for (int packet=0;packet<5;++packet) {
                for (int j=0;j<3;++j)
                    coarse_float_add(samples+2*j,real,imag,taps,inv[j],original+12*j);
                leo_coarse_triplet(samples,real,imag,taps,inv,candidate);
                assert(memcmp(original,candidate,sizeof(original))==0);
            }
        }
    }
    return 0;
}
