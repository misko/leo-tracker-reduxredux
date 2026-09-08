#include "../../src/leo/analysis/native_presence/ci16_lag.h"

void test_ci16_lag(const int16_t *iq, size_t count, size_t lag, double *out)
{
    double complex sum=ci16_lag_sum(iq,count,lag);
    out[0]=creal(sum); out[1]=cimag(sum);
}

#ifdef LEO_TEST_LAG_MAIN
#include <stdio.h>
#include <stdlib.h>
int main(void)
{
    int16_t *storage=calloc(200002,sizeof(int16_t));
    if (!storage) return 2;
    const size_t counts[]={7,50000,100000}, lags[]={0,3,256,16384};
    int checks=0;
    for (size_t offset=0; offset<2; ++offset) for (int kind=0; kind<3; ++kind) {
        int16_t *iq=storage+offset;
        for (size_t k=0; k<200000; ++k) {
            if (kind==0) iq[k]=-32768;
            else if (kind==1) iq[k]=(k&1) ? 32767 : -32768;
            else iq[k]=(int16_t)((int)((k*7919+12345)%65536)-32768);
        }
        for (int n=0; n<3; ++n) for (int l=0; l<4; ++l) {
            size_t count=counts[n], lag=lags[l];
            if (lag>=count) continue;
            int64_t real=0,imag=0;
            for (size_t k=0; k<count-lag; ++k) {
                int64_t ar=iq[2*k],ai=iq[2*k+1],br=iq[2*(k+lag)],bi=iq[2*(k+lag)+1];
                real+=ar*br+ai*bi; imag+=ar*bi-ai*br;
            }
            double complex got=ci16_lag_sum(iq,count,lag);
            if (creal(got)!=(double)real || cimag(got)!=(double)imag) {
                fprintf(stderr,"lag mismatch: %zu %d %zu %zu\n",offset,kind,count,lag);
                free(storage); return 1;
            }
            ++checks;
        }
    }
    printf("exact CI16 lag checks passed: %d\n",checks);
    free(storage); return 0;
}
#endif
