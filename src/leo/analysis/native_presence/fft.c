/* Small bounded radix-2/5 FFT, including linear pilot-power correlations.
 * No allocation or trigonometric generation occurs during execution. */
#include "fft.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef LEO_PRESENCE_FFTW
#define LEO_PRESENCE_FFTW 0
#endif
#if LEO_PRESENCE_FFTW != 0 && LEO_PRESENCE_FFTW != 1
#error "LEO_PRESENCE_FFTW must be 0 or 1"
#endif
#if LEO_PRESENCE_FFTW
#include <fftw3.h>
#endif

#ifndef LEO_PRESENCE_ITERATIVE_FFT
#define LEO_PRESENCE_ITERATIVE_FFT 0
#endif
#if LEO_PRESENCE_ITERATIVE_FFT != 0 && LEO_PRESENCE_ITERATIVE_FFT != 1
#error "LEO_PRESENCE_ITERATIVE_FFT must be 0 or 1"
#endif

const char *leo_fft_backend_identity(void)
{
#if LEO_PRESENCE_FFTW
    return fftw_version;
#else
    return "leo_builtin_fp64";
#endif
}

int leo_fft_init(leo_fft *fft, size_t size)
{
    size_t rest = size;
    memset(fft, 0, sizeof(*fft));
    if (size < 2 || size > 32768) return -1;
    while (rest % 2 == 0) rest /= 2;
    while (rest % 5 == 0) rest /= 5;
    if (rest != 1) return -1;
    fft->size = size;
#if LEO_PRESENCE_FFTW
    /* Fixed arrays avoid new-array alignment restrictions and allow caller
     * input to alias prior output. ESTIMATE planning happens only at setup;
     * no timed planner search or external wisdom import occurs here. The
     * owner serializes initialization/destruction, outside capture. */
    fft->output = fftw_alloc_complex(size);
    fft->scratch = fftw_alloc_complex(size);
    if (fft->output && fft->scratch)
        fft->backend_plan = fftw_plan_dft_1d((int)size, fft->scratch, fft->output,
            FFTW_FORWARD, FFTW_ESTIMATE);
    if (!fft->backend_plan) { leo_fft_free(fft); return -1; }
    return 0;
#else
    fft->roots = calloc(size, sizeof(double complex));
    fft->output = calloc(size, sizeof(double complex));
    fft->scratch = calloc(size, sizeof(double complex));
    if (!fft->roots || !fft->output || !fft->scratch) {
        leo_fft_free(fft);
        return -1;
    }
    for (size_t k = 0; k < size; ++k) {
        double angle = -6.283185307179586476925286766559 * k / size;
        fft->roots[k] = cos(angle) + I * sin(angle);
    }
    return 0;
#endif
}

void leo_fft_free(leo_fft *fft)
{
#if LEO_PRESENCE_FFTW
    if (fft->backend_plan) fftw_destroy_plan(fft->backend_plan);
    fftw_free(fft->output);
    fftw_free(fft->scratch);
#else
    free(fft->roots); free(fft->output); free(fft->scratch);
#endif
    memset(fft, 0, sizeof(*fft));
}

#if !LEO_PRESENCE_FFTW
static void transform(const leo_fft *fft, const double complex *input,
    size_t stride, size_t n, double complex *output, double complex *scratch)
{
    if (n == 1) { output[0] = input[0]; return; }
    size_t radix, m;
    if (n % 2 == 0) { radix=2; m=n/2; }
    else { radix=5; m=n/5; }
    for (size_t j = 0; j < radix; ++j)
        transform(fft, input + j * stride, stride * radix, m,
            output + j * m, scratch + j * m);
    /* stride is exactly size/n. Avoid integer division and modulo in every
     * butterfly; Cortex-A9 otherwise calls software division helpers here. */
    if (radix == 2) {
        for (size_t k = 0; k < m; ++k) {
            double complex even = output[k];
            double complex odd = output[m+k] * fft->roots[k*stride];
            scratch[k] = even+odd;
            scratch[m+k] = even-odd;
        }
    } else {
        for (size_t k = 0; k < m; ++k) {
            for (size_t branch = 0; branch < 5; ++branch) {
                size_t twiddle_step = (k+branch*m)*stride;
                size_t twiddle = twiddle_step;
                double complex value = output[k];
                for (size_t j = 1; j < 5; ++j) {
                    value += output[j*m+k]*fft->roots[twiddle];
                    twiddle += twiddle_step;
                    if (twiddle >= fft->size) twiddle -= fft->size;
                }
                scratch[branch*m+k] = value;
            }
        }
    }
    memcpy(output, scratch, n * sizeof(*output));
}

#if LEO_PRESENCE_ITERATIVE_FFT
static void transform_radix2(leo_fft *fft, const double complex *input)
{
    const size_t n = fft->size;
    double complex *output = fft->output;
    /* The same FP64 butterflies and root table as the recursive path, but
     * without per-level copies and per-leaf function calls. The permutation
     * is bounded by n; no plan allocation or trigonometry occurs here. */
    for (size_t i = 0, reversed = 0; i < n; ++i) {
        if (input != output) output[reversed] = input[i];
        else if (i < reversed) {
            double complex value = output[i];
            output[i] = output[reversed];
            output[reversed] = value;
        }
        size_t bit = n >> 1;
        while (bit && (reversed & bit)) { reversed ^= bit; bit >>= 1; }
        reversed ^= bit;
    }
    for (size_t width = 2, stride = n >> 1; width <= n; width <<= 1, stride >>= 1) {
        size_t half = width >> 1;
        for (size_t base = 0; base < n; base += width) {
            for (size_t k = 0; k < half; ++k) {
                double complex even = output[base+k];
                double complex odd = output[base+half+k] * fft->roots[k*stride];
                output[base+k] = even+odd;
                output[base+half+k] = even-odd;
            }
        }
    }
}
#endif

#endif

void leo_fft_forward(leo_fft *fft, const double complex *input)
{
#if LEO_PRESENCE_FFTW
    if (input != fft->scratch)
        memcpy(fft->scratch,input,fft->size*sizeof(*input));
    fftw_execute(fft->backend_plan);
#else
#if LEO_PRESENCE_ITERATIVE_FFT
    if ((fft->size & (fft->size-1)) == 0) {
        transform_radix2(fft, input);
        return;
    }
#endif
    transform(fft, input, 1, fft->size, fft->output, fft->scratch);
#endif
}
