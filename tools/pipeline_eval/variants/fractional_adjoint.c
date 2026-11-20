/* Evaluate the two transposed Lanczos templates on the original IQ grid. */
#include <stdint.h>

enum { symbols = 64, spacing = 44, taps = 59 };

void paired_adjoint(const double *restrict iq, const double *restrict references,
                    const int32_t *restrict starts, int frames, double *restrict out)
{
    for (int f = 0; f < frames; ++f)
        for (int s = 0; s < symbols; ++s) {
            const double *x = iq + 2 * (starts[f] + s * spacing);
            const double *exact = references + 2 * s * taps;
            const double *control = exact + 2 * symbols * taps;
            double er = 0, ei = 0, cr = 0, ci = 0;
            #pragma omp simd reduction(+:er, ei, cr, ci)
            for (int i = 0; i < taps; ++i) {
                double xr = x[2*i], xi = x[2*i+1];
                double ar = exact[2*i], ai = exact[2*i+1];
                double br = control[2*i], bi = control[2*i+1];
                er += xr * ar - xi * ai;
                ei += xr * ai + xi * ar;
                cr += xr * br - xi * bi;
                ci += xr * bi + xi * br;
            }
            int p = 2 * (f * symbols + s);
            out[p] = er;
            out[p+1] = ei;
            out[p + 2 * frames * symbols] = cr;
            out[p + 2 * frames * symbols + 1] = ci;
        }
}
