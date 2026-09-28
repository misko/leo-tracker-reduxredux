#ifndef LEO_DECISION_DECIMATOR_FFT_H
#define LEO_DECISION_DECIMATOR_FFT_H
#include <stddef.h>
#include <stdint.h>
/* Private research overlap-save factor-four FIR backend. No rate, filter,
 * support, phase or detector-policy changes. FP32 arithmetic requires explicit
 * qualification against the scalar integer convolution. */
typedef struct leo_decimator_fft leo_decimator_fft;
leo_decimator_fft *leo_decimator_fft_create(const int16_t *, unsigned, size_t);
void leo_decimator_fft_destroy(leo_decimator_fft *);
int leo_decimator_fft_run(leo_decimator_fft *, const int16_t *, size_t, int16_t *);
#endif
