#ifndef LEO_PRESENCE_FFT_H
#define LEO_PRESENCE_FFT_H
#include <complex.h>
#include <stddef.h>
typedef struct {
    size_t size;
    double complex *roots, *output, *scratch;
} leo_fft;
int leo_fft_init(leo_fft *fft, size_t size);
void leo_fft_free(leo_fft *fft);
void leo_fft_forward(leo_fft *fft, const double complex *input);
#endif
