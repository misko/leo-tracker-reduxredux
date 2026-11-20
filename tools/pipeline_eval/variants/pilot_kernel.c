/* Accumulate each complex product component in its own vector register. */
#include <math.h>
#include <stdint.h>
#include <string.h>

enum { lanes = 8, vectors = 2, tile = vectors * lanes };
typedef float iq_vector __attribute__((vector_size(lanes * sizeof(float))));

static inline void read_vector(iq_vector *result, const float *values)
{
    memcpy(result, values, sizeof(*result));
}

static inline void fold_tile(
    const float *real, const float *imag, const float *cr, const float *ci,
    int taps, const float *inverse_norm, double *scores)
{
    iq_vector rr[vectors] = {{0}}, ii[vectors] = {{0}};
    iq_vector ri[vectors] = {{0}}, ir[vectors] = {{0}};
    for (int t = 0; t < taps; ++t) {
        #pragma GCC unroll 2
        for (int v = 0; v < vectors; ++v) {
            iq_vector xr, xi;
            read_vector(&xr, real + t + v * lanes);
            read_vector(&xi, imag + t + v * lanes);
            rr[v] += xr * cr[t];
            ii[v] += xi * ci[t];
            ri[v] += xr * ci[t];
            ir[v] += xi * cr[t];
        }
    }
    for (int v = 0; v < vectors; ++v) {
        iq_vector re = rr[v] - ii[v], im = ri[v] + ir[v];
        #pragma omp simd
        for (int k = 0; k < lanes; ++k) {
            int offset = v * lanes + k;
            scores[offset] += sqrtf(re[k] * re[k] + im[k] * im[k]) * inverse_norm[offset];
        }
    }
}

void fold_filter_bank(
    const float *restrict real, const float *restrict imag, int samples,
    const float *restrict coeff_real, const float *restrict coeff_imag,
    int filters, int taps, int symbol_start, const int32_t *restrict frames,
    int frame_count, const float *restrict inverse_norm, int epochs,
    double *restrict scores, int32_t *restrict support)
{
    for (int j = 0; j < frame_count; ++j) {
        int origin = frames[j] + symbol_start;
        int n = samples - taps + 1 - origin;
        if (n > epochs) n = epochs;
        for (int e = 0; e < n; ++e) support[e]++;
        for (int f = 0; f < filters; ++f) {
            const float *cr = coeff_real + f * taps;
            const float *ci = coeff_imag + f * taps;
            double *row = scores + f * epochs;
            int e = 0;
            for (; e <= n - tile; e += tile) {
                int start = origin + e;
                fold_tile(real + start, imag + start, cr, ci, taps,
                          inverse_norm + start, row + e);
            }
            for (; e < n; ++e) {
                int start = origin + e;
                float rr = 0, ii = 0, ri = 0, ir = 0;
                for (int t = 0; t < taps; ++t) {
                    float xr = real[start + t], xi = imag[start + t];
                    rr += xr * cr[t];
                    ii += xi * ci[t];
                    ri += xr * ci[t];
                    ir += xi * cr[t];
                }
                float re = rr - ii, im = ri + ir;
                row[e] += sqrtf(re * re + im * im) * inverse_norm[start];
            }
        }
    }
}
