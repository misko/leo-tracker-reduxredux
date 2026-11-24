#include "grid_feature_projection.c"

/* The two projections share input loads while preserving each binary64 row's
 * original reduction and each direction's independent output arrays. */
int project_secant_pair(size_t rows, const double *observer, const double *p, const double *v,
                        const double *pp, const double *vp, const double *pm, const double *vm,
                        const double *dp, const double *dv, double *line, double *frequency,
                        double *difference, double *modes) {
    for (size_t i = 0; i < rows; ++i) {
        const size_t j = 3 * i;
        for (size_t a = 0; a < 2; ++a) {
            const double *o = observer + 3 * a;
            const size_t at = a * rows + i;
            double *l = line + 3 * at;
            const double range = relative(p + j, o, l);
            if (!(range > 0.0) || !isfinite(range)) {
                return 0;
            }
            frequency[at] = (carrier * (dot(l, v + j) / range)) / c_km_s;
            difference[at] = (shifted(pp + j, vp + j, o) - shifted(pm + j, vm + j, o)) / 0.02;
            double direction[3], gradient[3];
            for (size_t k = 0; k < 3; ++k) {
                direction[k] = l[k] / range;
            }
            const double rate = ((direction[0] * v[j] + direction[1] * v[j + 1])
                                 + direction[2] * v[j + 2]) + 0.0;
            for (size_t k = 0; k < 3; ++k) {
                gradient[k] = (v[j + k] - rate * direction[k]) / range;
            }
            for (size_t k = 0; k < 3; ++k) {
                const size_t mode = 3 * (j + k);
                modes[3 * at + k] = (carrier / c_km_s)
                    * (dot(gradient, dp + mode) + dot(direction, dv + mode));
                if (!isfinite(modes[3 * at + k])) {
                    return 0;
                }
            }
            if (!isfinite(frequency[at]) || !isfinite(difference[at])) {
                return 0;
            }
        }
    }
    return 1;
}
