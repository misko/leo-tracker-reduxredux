#ifndef LEO_DECIMATED_FIR_H
#define LEO_DECIMATED_FIR_H
#include <complex.h>
#include <stddef.h>
enum { LEO_DECIMATION=5, LEO_DECIMATED_TAPS=24 };
void leo_decimated_filter(float h[LEO_DECIMATED_TAPS]);
void leo_decimated_modulate(const float h[LEO_DECIMATED_TAPS],double rate,
    double center,float complex mh[LEO_DECIMATED_TAPS],float complex *step);
size_t leo_decimate_scalar(const float complex *x,size_t n,
    const float complex mh[LEO_DECIMATED_TAPS],float complex step,float complex *out);
size_t leo_decimate_neon(const float complex *x,size_t n,
    const float complex mh[LEO_DECIMATED_TAPS],float complex step,float complex *out);
#endif
