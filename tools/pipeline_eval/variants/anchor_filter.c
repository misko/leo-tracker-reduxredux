/* Fold normalized short-filter magnitudes at the recorded frame offsets. */
#include <math.h>
#include <stdint.h>

void fold_filter_bank(
    const float *restrict real, const float *restrict imag, int samples,
    const float *restrict coeff_real, const float *restrict coeff_imag,
    int filters, int taps, int symbol_start, const int32_t *restrict frames,
    int frame_count, const float *restrict inverse_norm, int epochs,
    double *restrict scores, int32_t *restrict support)
{
    enum { block = 32 };
    for (int j = 0; j < frame_count; ++j) {
        int origin = frames[j] + symbol_start;
        int n = samples - taps + 1 - origin;
        if (n > epochs) n = epochs;
        for (int i = 0; i < n; ++i) support[i]++;
        for (int f = 0; f < filters; ++f) {
            const float *cr = coeff_real + f * taps;
            const float *ci = coeff_imag + f * taps;
            for (int e = 0; e < n; e += block) {
                float re[block] = {0};
                float im[block] = {0};
                int count = n-e < block ? n-e : block;
                for (int t = 0; t < taps; ++t) {
                    const float *xr = real + origin + e + t;
                    const float *xi = imag + origin + e + t;
                    #pragma omp simd
                    for (int k = 0; k < count; ++k) {
                        re[k] += xr[k] * cr[t] - xi[k] * ci[t];
                        im[k] += xr[k] * ci[t] + xi[k] * cr[t];
                    }
                }
                #pragma omp simd
                for (int k = 0; k < count; ++k) {
                    float magnitude = sqrtf(re[k]*re[k] + im[k]*im[k]);
                    scores[f*epochs+e+k] += magnitude * inverse_norm[origin+e+k];
                }
            }
        }
    }
}
