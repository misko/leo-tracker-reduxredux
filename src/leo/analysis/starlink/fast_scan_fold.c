/* Research kernel: CI16 -> centered lag-one products folded over 4 ms.
 * No CFO hypotheses, timing estimates, or GLRT labels enter this operation.
 * Build with -O3 -fPIC -shared -ffp-contract=off; do not use -ffast-math.
 */
#include <stdint.h>
#include <string.h>

int fast8_fold_ci16(const int16_t *iq, int receivers, double *fold, double *energy) {
    if (!iq || !fold || !energy || receivers < 1 || receivers > 2) return -1;
    const int n = 50000, period = 10000;
    const int stride = receivers * 2;
    memset(fold, 0, (size_t)receivers * period * 2 * sizeof(double));
    for (int rx = 0; rx < receivers; ++rx) {
        double sr = 0, si = 0;
        for (int j = 1; j < n; ++j) {
            const int p = j * stride + 2 * rx;
            const double ar = iq[p], ai = iq[p + 1];
            const double br = iq[p - stride], bi = iq[p - stride + 1];
            sr += ar * br + ai * bi;
            si += ai * br - ar * bi;
        }
        const double mr = sr / (n - 1), mi = si / (n - 1);
        double e = 0;
        double *out = fold + rx * period * 2;
        /* A second pass avoids catastrophic cancellation in E[z^2]-E[z]^2
         * for constant or nearly constant input. Products cannot overflow:
         * CI16 operands are converted to double before multiplication.
         */
        for (int j = 1; j < n; ++j) {
            const int p = j * stride + 2 * rx;
            const double ar = iq[p], ai = iq[p + 1];
            const double br = iq[p - stride], bi = iq[p - stride + 1];
            const double zr = ar * br + ai * bi - mr;
            const double zi = ai * br - ar * bi - mi;
            const int k = (j % period) * 2;
            out[k] += zr;
            out[k + 1] += zi;
            e += zr * zr + zi * zi;
        }
        energy[rx] = e;
    }
    return 0;
}
