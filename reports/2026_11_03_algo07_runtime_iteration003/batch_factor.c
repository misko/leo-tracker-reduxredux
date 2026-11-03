/* Diagnostic prototype only. No fast-math or reduction approximation. */
#include <math.h>
#include <stddef.h>

int batch_factor(const double *gram, const double *rhs, double *coef,
                 double *logdet, size_t count, int d) {
    if (d < 1 || d > 32) return -1;
    for (size_t n = 0; n < count; ++n) {
        const double *g = gram + n * d * d;
        const double *b = rhs + n * d;
        double *x = coef + n * d;
        double l[32 * 32], z[32];
        double ld = 0.0;
        for (int i = 0; i < d; ++i) {
            for (int j = 0; j <= i; ++j) {
                double v = g[i * d + j];
                for (int k = 0; k < j; ++k)
                    v -= l[i * d + k] * l[j * d + k];
                if (i == j) {
                    if (!(v > 0.0) || !isfinite(v)) return (int)n + 1;
                    l[i * d + j] = sqrt(v);
                    ld += log(l[i * d + j]);
                } else {
                    l[i * d + j] = v / l[j * d + j];
                }
            }
            double v = b[i];
            for (int j = 0; j < i; ++j) v -= l[i * d + j] * z[j];
            z[i] = v / l[i * d + i];
        }
        for (int i = d - 1; i >= 0; --i) {
            double v = z[i];
            for (int j = i + 1; j < d; ++j) v -= l[j * d + i] * x[j];
            x[i] = v / l[i * d + i];
        }
        logdet[n] = 2.0 * ld;
    }
    return 0;
}
