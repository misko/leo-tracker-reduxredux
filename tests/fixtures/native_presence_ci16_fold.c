/* Test-only adapter exposes exact fold sums before any normalization/search. */
#include <complex.h>
#include <stddef.h>
#include <stdint.h>
#include <math.h>
#define LEO_PRESENCE_DIFFERENTIAL_LAG 4
typedef struct {
    uint32_t rate;
    size_t n;
    double *power_native_folded;
    double complex *diff_folded;
    int32_t *support, *diff_support;
} leo_presence_workspace;
static int frame_start(const leo_presence_workspace *w, int epoch, int frame)
{ return epoch+(int)nearbyint(frame*(w->rate/750.0)); }
#include "../../src/leo/analysis/native_presence/ci16_fold.h"
void test_ci16_fold(uint32_t rate, const int16_t *iq, size_t count,
    double *power, double complex *diff, int32_t *support, int32_t *diff_support)
{
    leo_presence_workspace w={rate,(size_t)nearbyint(rate/750.0),power,diff,support,diff_support};
    coarse_fold_ci16(&w,iq,count);
}

#ifdef LEO_PRESENCE_FOLD_SELFTEST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Bounded synthetic-only ARM test. Independent scalar frame-major integer
 * reference checks every SIMD output cell, including full-scale products. */
int main(void)
{
    int16_t *iq=malloc(200000*sizeof(*iq));
    double *p=malloc(6667*sizeof(*p));
    double complex *d=malloc(6667*sizeof(*d));
    int32_t *s=malloc(6667*sizeof(*s)), *ds=malloc(6667*sizeof(*ds));
    if (!iq || !p || !d || !s || !ds) return 2;
    unsigned checks=0;
    for (uint32_t rate=2500000; rate<=5000000; rate*=2) {
        size_t n=(size_t)nearbyint(rate/750.0);
        size_t lengths[3]={(size_t)ceil(rate/375.0),rate/50-7,rate/50};
        for (unsigned length=0; length<3; ++length) for (unsigned kind=0; kind<4; ++kind) {
            size_t count=lengths[length];
            uint32_t random=735;
            for (size_t k=0; k<2*count; ++k) {
                random=1664525u*random+1013904223u;
                iq[k]=kind==0 ? (int16_t)(random>>16) : kind==1 ? -32768 :
                    kind==2 ? (((k/2+k%2)&1) ? 32767 : -32768) : 0;
            }
            test_ci16_fold(rate,iq,count,p,d,s,ds);
            for (size_t k=0; k<n; ++k) {
                int64_t power=0, real=0, imag=0;
                int32_t support=0, diff_support=0;
                for (unsigned frame=0; frame<16; ++frame) {
                    size_t offset=(size_t)nearbyint(frame*(rate/750.0))+k;
                    if (offset>=count) break;
                    int64_t ar=iq[2*offset], ai=iq[2*offset+1];
                    power+=ar*ar+ai*ai; ++support;
                    if (offset+4<count) {
                        int64_t br=iq[2*(offset+4)], bi=iq[2*(offset+4)+1];
                        real+=ar*br+ai*bi; imag+=ar*bi-ai*br; ++diff_support;
                    }
                }
                if (p[k]!=(double)power || creal(d[k])!=(double)real ||
                    cimag(d[k])!=(double)imag || s[k]!=support || ds[k]!=diff_support) {
                    fprintf(stderr,"fold mismatch rate=%u length=%zu kind=%u cell=%zu\n",
                        rate,count,kind,k);
                    return 1;
                }
            }
            ++checks;
        }
    }
    free(iq); free(p); free(d); free(s); free(ds);
    printf("{\"exact_fold_cases\":%u,\"status\":\"all_cells_match_scalar_reference\"}\n",checks);
    return 0;
}
#endif
