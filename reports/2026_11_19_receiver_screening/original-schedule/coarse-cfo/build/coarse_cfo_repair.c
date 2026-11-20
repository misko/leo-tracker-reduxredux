/* Direct full-template recomputation of requested folded CFO/epoch cells. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

void coarse_cfo_cells(const double *iq, const double *normalization, const double *coefficients,
    const int32_t *anchors, const int32_t *frames, int ns, int nf, int samples, const int32_t *cells,
    int count, int epochs, double *out)
{
    for (int j = 0; j < count; ++j) {
        const int row = cells[j] / epochs, epoch = cells[j] % epochs;
        double sum = 0;
        int support = 0;
        for (int s = 0; s < ns; ++s) {
            const double *filter = coefficients + (size_t)(row * ns + s) * 88;
            for (int f = 0; f < nf; ++f) {
                const int base = epoch + anchors[s] + frames[f];
                if (base + 44 > samples) break;
                double real = 0, imag = 0;
                const double *wave = iq + (size_t)2 * base;
                #pragma omp simd reduction(+:real,imag)
                for (int t = 0; t < 44; ++t) {
                    real += wave[2*t]*filter[2*t] - wave[2*t+1]*filter[2*t+1];
                    imag += wave[2*t]*filter[2*t+1] + wave[2*t+1]*filter[2*t];
                }
                sum += sqrt(real*real + imag*imag) * normalization[base];
                ++support;
            }
        }
        out[cells[j]] = support ? sum / support : 0;
    }
}
