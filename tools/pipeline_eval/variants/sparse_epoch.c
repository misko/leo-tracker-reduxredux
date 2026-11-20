/* Six exact ADC phases make sparse epoch starts contiguous within each SIMD lane. */
#include "spectral_grid.c"

enum { stride = 6 };

void score_sparse_epochs(
    const float *restrict real, const float *restrict imag, int plane, int valid,
    const float *restrict coeff_real, const float *restrict coeff_imag, int filters,
    int taps, const int32_t *restrict anchors, int anchor_count,
    const int32_t *restrict frames, int frame_count, const float *restrict inverse_norm,
    int epochs, double *restrict scores)
{
    int columns = (epochs + stride - 1) / stride;
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        for (int j = 0; j < frame_count; ++j) {
            int origin = frames[j] + anchors[anchor];
            int raw_count = valid - origin;
            if (raw_count > epochs) raw_count = epochs;
            if (raw_count <= 0) continue;
            int n = (raw_count + stride - 1) / stride;
            int offsets[taps];
            for (int t = 0; t < taps; ++t) {
                int start = origin + t;
                offsets[t] = start % stride * plane + start / stride;
            }
            const float *norm = inverse_norm + offsets[0];
            for (int f = 0; f < filters; ++f) {
                const float *cr = coeff_real + (f * anchor_count + anchor) * taps;
                const float *ci = coeff_imag + (f * anchor_count + anchor) * taps;
                double *row = scores + f * columns;
                int e = 0;
                for (; e <= n - tile; e += tile) {
                    iq_vector rr[vectors] = {{0}}, ii[vectors] = {{0}};
                    iq_vector ri[vectors] = {{0}}, ir[vectors] = {{0}};
                    for (int t = 0; t < taps; ++t) {
                        const float *xr = real + offsets[t] + e;
                        const float *xi = imag + offsets[t] + e;
                        #pragma GCC unroll 2
                        for (int v = 0; v < vectors; ++v) {
                            iq_vector r, i;
                            read_vector(&r, xr + v * lanes);
                            read_vector(&i, xi + v * lanes);
                            rr[v] += r * cr[t];
                            ii[v] += i * ci[t];
                            ri[v] += r * ci[t];
                            ir[v] += i * cr[t];
                        }
                    }
                    for (int v = 0; v < vectors; ++v) {
                        iq_vector re = rr[v] - ii[v], im = ri[v] + ir[v];
                        #pragma omp simd
                        for (int k = 0; k < lanes; ++k) {
                            int offset = e + v * lanes + k;
                            row[offset] += sqrtf(re[k] * re[k] + im[k] * im[k]) * norm[offset];
                        }
                    }
                }
                for (; e < n; ++e) {
                    float rr = 0, ii = 0, ri = 0, ir = 0;
                    for (int t = 0; t < taps; ++t) {
                        float xr = real[offsets[t] + e], xi = imag[offsets[t] + e];
                        rr += xr * cr[t];
                        ii += xi * ci[t];
                        ri += xr * ci[t];
                        ir += xi * cr[t];
                    }
                    float re = rr - ii, im = ri + ir;
                    row[e] += sqrtf(re * re + im * im) * norm[e];
                }
            }
        }
    }
}
