/* Arrowhead bounded least squares for fixed receiver/orbit associations. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define RECEIVER_WIDTH 11

/* Symmetric Gram matrices use row-major order. Each orbit row contains its
 * receiver cross terms, its own diagonal, and its right-hand side. */
static int factor(size_t n, double a[RECEIVER_WIDTH][RECEIVER_WIDTH], double *scale)
{
    for (size_t i = 0; i < n; ++i) {
        if (!(a[i][i] > 0.0) || !isfinite(a[i][i]))
            return 0;
        scale[i] = sqrt(a[i][i]);
    }
    for (size_t i = 0; i < n; ++i) {
        for (size_t j = 0; j <= i; ++j) {
            double entry = a[i][j] / (scale[i] * scale[j]);
            for (size_t k = 0; k < j; ++k)
                entry -= a[i][k] * a[j][k];
            if (i == j) {
                if (!(entry > 0.0) || !isfinite(entry))
                    return 0;
                a[i][i] = sqrt(entry);
            } else {
                a[i][j] = entry / a[j][j];
            }
        }
    }
    return 1;
}

static void substitute(size_t n, double a[RECEIVER_WIDTH][RECEIVER_WIDTH],
                       const double *scale, double *rhs)
{
    for (size_t i = 0; i < n; ++i) {
        rhs[i] /= scale[i];
        for (size_t j = 0; j < i; ++j)
            rhs[i] -= a[i][j] * rhs[j];
        rhs[i] /= a[i][i];
    }
    for (size_t i = n; i-- > 0;) {
        for (size_t j = i + 1; j < n; ++j)
            rhs[i] -= a[j][i] * rhs[j];
        rhs[i] /= a[i][i];
    }
    for (size_t i = 0; i < n; ++i)
        rhs[i] /= scale[i];
}

static int reduced_fit(size_t width, size_t orbits, const double *gram, const double *rhs,
                       const double *orbit, const int8_t *active, const double *x,
                       double *trial, double *covariance)
{
    size_t free[RECEIVER_WIDTH], count = 0;
    double a[RECEIVER_WIDTH][RECEIVER_WIDTH], b[RECEIVER_WIDTH], scale[RECEIVER_WIDTH] = {0};
    for (size_t j = 0; j < width; ++j)
        if (!active[j])
            free[count++] = j;
    for (size_t i = 0; i < count; ++i) {
        size_t j = free[i];
        b[i] = rhs[j];
        for (size_t k = 0; k < width; ++k)
            if (active[k])
                b[i] -= gram[j * width + k] * x[k];
        for (size_t k = 0; k <= i; ++k)
            a[i][k] = gram[j * width + free[k]];
    }
    for (size_t p = 0; p < orbits; ++p) {
        const double *col = orbit + p * (width + 2);
        if (active[width + p]) {
            for (size_t i = 0; i < count; ++i)
                b[i] -= col[free[i]] * x[width + p];
            continue;
        }
        double orbit_rhs = col[width + 1];
        for (size_t j = 0; j < width; ++j)
            if (active[j])
                orbit_rhs -= col[j] * x[j];
        for (size_t i = 0; i < count; ++i) {
            double scale_by_diagonal = col[free[i]] / col[width];
            b[i] -= scale_by_diagonal * orbit_rhs;
            for (size_t k = 0; k <= i; ++k)
                a[i][k] -= scale_by_diagonal * col[free[k]];
        }
    }
    if (!factor(count, a, scale))
        return 0;
    substitute(count, a, scale, b);
    memcpy(trial, x, (width + orbits) * sizeof(*trial));
    for (size_t i = 0; i < count; ++i)
        trial[free[i]] = b[i];
    for (size_t p = 0; p < orbits; ++p) {
        const double *col = orbit + p * (width + 2);
        if (!active[width + p]) {
            double orbit_rhs = col[width + 1];
            for (size_t j = 0; j < width; ++j)
                orbit_rhs -= col[j] * trial[j];
            trial[width + p] = orbit_rhs / col[width];
        }
    }
    /* The original radius uses the unbounded Fisher covariance even when the
     * estimate has an active bound. The first reduced solve is unconstrained. */
    if (covariance != NULL) {
        for (size_t i = 0; i < 2; ++i) {
            double unit[RECEIVER_WIDTH] = {0};
            unit[i] = 1.0;
            substitute(count, a, scale, unit);
            covariance[2 * i] = unit[0];
            covariance[2 * i + 1] = unit[1];
        }
    }
    return 1;
}

static double optimality(size_t width, size_t orbits, const double *gram, const double *rhs,
                         const double *orbit, const int8_t *active, const double *x,
                         size_t *release)
{
    double worst = 0.0, worst_active = 0.0;
    *release = width + orbits;
    for (size_t j = 0; j < width + orbits; ++j) {
        double gradient, diagonal;
        if (j < width) {
            diagonal = gram[j * width + j];
            gradient = -rhs[j];
            for (size_t k = 0; k < width; ++k)
                gradient += gram[j * width + k] * x[k];
            for (size_t p = 0; p < orbits; ++p)
                gradient += orbit[p * (width + 2) + j] * x[width + p];
        } else {
            const double *col = orbit + (j - width) * (width + 2);
            diagonal = col[width];
            gradient = diagonal * x[j] - col[width + 1];
            for (size_t k = 0; k < width; ++k)
                gradient += col[k] * x[k];
        }
        double violation = (active[j] ? gradient * active[j] : fabs(gradient)) / sqrt(diagonal);
        if (active[j] && violation > worst_active) {
            worst_active = violation;
            *release = j;
        }
        worst = fmax(worst, violation);
    }
    if (worst_active <= 1e-9)
        *release = width + orbits;
    return worst;
}

/* Return zero on success, one for bad dimensions/input, two for an unusable
 * Schur factor, or three if convergence could not be certified. */
int leo_embedded_bvls(size_t width, size_t orbits, const double *gram, const double *rhs,
                      const double *orbit, const double *bound, double *x,
                      double *covariance, double *kkt, size_t *steps)
{
    if (width < 2 || width > RECEIVER_WIDTH || orbits > 4096)
        return 1;
    size_t n = width + orbits;
    for (size_t j = 0; j < width; ++j) {
        if (!isfinite(rhs[j]) || !(gram[j * width + j] > 0.0))
            return 1;
        for (size_t k = 0; k < width; ++k)
            if (!isfinite(gram[j * width + k]))
                return 1;
    }
    for (size_t j = 0; j < n; ++j)
        if (!(bound[j] > 0.0) || !isfinite(bound[j]))
            return 1;
    for (size_t p = 0; p < orbits; ++p) {
        const double *col = orbit + p * (width + 2);
        if (!(col[width] > 0.0))
            return 1;
        for (size_t j = 0; j < width + 2; ++j)
            if (!isfinite(col[j]))
                return 1;
    }
    double *trial = malloc(n * sizeof(*trial));
    int8_t *active = calloc(n, sizeof(*active));
    int ret = 1;
    if (trial == NULL || active == NULL)
        goto done;
    memset(x, 0, n * sizeof(*x));
    for (*steps = 0; *steps < 32 * n; ++*steps) {
        if (!reduced_fit(width, orbits, gram, rhs, orbit, active, x, trial,
                         *steps == 0 ? covariance : NULL)) {
            ret = 2;
            goto done;
        }
        double alpha = 1.0;
        size_t hit = n;
        for (size_t j = 0; j < n; ++j) {
            if (!isfinite(trial[j]))
                goto done;
            if (fabs(trial[j]) > bound[j]) {
                double edge = copysign(bound[j], trial[j]);
                double candidate = (edge - x[j]) / (trial[j] - x[j]);
                if (candidate <= alpha) {
                    alpha = fmax(0.0, candidate);
                    hit = j;
                }
            }
        }
        if (hit != n) {
            for (size_t j = 0; j < n; ++j)
                x[j] = fmin(bound[j], fmax(-bound[j], x[j] + alpha * (trial[j] - x[j])));
            active[hit] = trial[hit] > 0.0 ? 1 : -1;
            x[hit] = active[hit] * bound[hit];
            continue;
        }
        memcpy(x, trial, n * sizeof(*x));
        size_t release;
        *kkt = optimality(width, orbits, gram, rhs, orbit, active, x, &release);
        if (release == n) {
            ret = *kkt <= 1e-8 ? 0 : 3;
            goto done;
        }
        active[release] = 0;
    }
    ret = 3;
done:
    free(active);
    free(trial);
    return ret;
}
