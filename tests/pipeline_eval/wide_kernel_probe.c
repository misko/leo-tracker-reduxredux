#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static double sinc(double x)
{
    const double pi = 3.141592653589793238462643383279502884;
    return x == 0.0 ? 1.0 : sin(pi*x)/(pi*x);
}

#include "fractional_runtime.h"
#include "wide_kernel_fractional.h"

int main(void)
{
#if LEO_WIDE_KERNEL_AVX2
    if (!__builtin_cpu_supports("avx2")) return 77;
    const double offsets[] = {-1.917, -0.7314283, 0.7314283, 1.9995, 0x1p-35};
    double complex input[80], output[64];
    for (int i=0; i<80; ++i)
        input[i] = (14*i-581) + I*((9132*i+639)%65536-32768);
    for (unsigned j=0; j<sizeof(offsets)/sizeof(offsets[0]); ++j) {
        leo_fractional_runtime filter = {.fraction = NAN};
        (void)leo_fractional_runtime_base(&filter,10248,offsets[j]);
        for (int size=1; size<=64; ++size) {
            leo_wide_fractional_block(&filter,input,size,output);
            for (int i=0; i<size; ++i) {
                const double complex expected = leo_fractional_runtime_dot(&filter,input+i);
                if (memcmp(&expected,output+i,sizeof(expected))) {
                    fprintf(stderr,"different ordered sum at length %d sample %d\n",size,i);
                    return 1;
                }
            }
        }
    }
#endif
    return 0;
}
