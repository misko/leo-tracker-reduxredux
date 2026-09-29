static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

int main(void) {
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    double maximum=0;
    for(int r=0;r<4;r++) {
        size_t n=(rates[r]+375)/750;
        float *weighted=calloc(2*n,sizeof(*weighted));assert(weighted);
        for(int pattern=0;pattern<5;pattern++) {
            double norm=0;
            for(size_t k=0;k<n;k++) {
                double phase=TAU*3713.0*k/rates[r];
                float re=0,im=0;
                if(pattern==1){re=cos(phase);im=sin(phase);}
                if(pattern==2){re=(float)((int)(k%19)-9)/9;im=(float)((int)(k%23)-11)/11;}
                if(pattern==3){re=k%2 ? -32768:32767;im=k%3 ? 32767:-32768;}
                if(pattern==4){re=k==0||k==n-1 ? 32767:0;im=k==CONDITIONED_MOMENT_BLOCK ? -32768:0;}
                weighted[2*k]=re;weighted[2*k+1]=im;norm+=hypot(re,im);
            }
            float actual[64];assert(!conditioned_moment_magnitudes(weighted,n,rates[r],41,actual));
            for(int f=0;f<41;f++) {
                double complex exact=0;
                for(size_t k=0;k<n;k++)exact+=((double)weighted[2*k]+I*weighted[2*k+1])*rotate(-TAU*100*f*k/rates[r]);
                double error=fabs(actual[f]-cabs(exact))/fmax(norm,1);
                double phase=TAU*100*f*.5*(CONDITIONED_MOMENT_BLOCK-1)/rates[r];
                double bound=exp(phase)*pow(phase,5)/120+2e-5;
                assert(isfinite(actual[f])&&error<=bound);
                if(error>maximum)maximum=error;
            }
        }
        free(weighted);
    }
    printf("wide block=%d direct DFT max normalized error=%.17g all_rates=4 patterns=5 bins=41\n",CONDITIONED_MOMENT_BLOCK,maximum);
    return 0;
}
