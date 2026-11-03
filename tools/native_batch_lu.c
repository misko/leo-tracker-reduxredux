/* Research-only batch wrapper. Reuse DGESV's LU for the determinant. */
#include <stdint.h>
#include <stddef.h>
#include <math.h>

typedef void (*dgesv64_fn)(int64_t *, int64_t *, double *, int64_t *,
                          int64_t *, double *, int64_t *, int64_t *);

int batch_lu(void *function, const double *gram, const double *rhs,
             double *coef, double *signs, double *logdet, size_t count, int d) {
    if (!function || !gram || !rhs || !coef || !signs || !logdet || d < 1 || d > 32)
        return -1;
    dgesv64_fn solve = (dgesv64_fn)function;
    int64_t n = d, nrhs = 1, leading = d;
    double a[32*32];
    int64_t pivots[32];
    for (size_t row = 0; row < count; ++row) {
        const double *g = gram + row*d*d;
        double *x = coef + row*d;
        for (int i = 0; i < d; ++i) {
            x[i] = rhs[row*d+i];
            for (int j = 0; j < d; ++j) a[j*d+i] = g[i*d+j];
        }
        int64_t info = 0;
        solve(&n, &nrhs, a, &leading, pivots, x, &leading, &info);
        if (info != 0) return info > 0 ? 1 : -2;
        double sign = 1.0, ld = 0.0;
        for (int i = 0; i < d; ++i) {
            if (pivots[i] != i+1) sign = -sign;
            double diagonal = a[i*d+i];
            if (diagonal < 0.0) { sign = -sign; diagonal = -diagonal; }
            ld += log(diagonal);
        }
        signs[row] = sign;
        logdet[row] = ld;
    }
    return 0;
}
