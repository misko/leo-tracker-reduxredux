/* Share only the immutable interpolation across two released observer projections. */
#include "orbit_projector.c"

static inline int project_observer(const double p[3], const double v[3],
                                   const double dp[3], const double dv[3],
                                   const double observer[3], const double up[3],
                                   double rf, double *frequency, double *elevation,
                                   double *derivative)
{
    double squared_range = 0, radial = 0, vertical = 0;
    double radial_change = 0, squared_range_half_change = 0;
    for (size_t j = 0; j < 3; ++j) {
        double delta = p[j] - observer[j];
        squared_range += delta * delta;
        radial += delta * v[j];
        vertical += delta * up[j];
        radial_change += dp[j] * v[j] + delta * dv[j];
        squared_range_half_change += delta * dp[j];
    }
    double range = sqrt(squared_range);
    if (!(range > 0) || !isfinite(range)) return 1;
    *frequency = -rf * (radial / range) / 299792.458;
    *elevation = vertical / range;
    *derivative = -rf * (radial_change / range -
                         radial * squared_range_half_change / (range * squared_range)) / 299792.458;
    return 0;
}

int project_orbit_pair(const double *pos, const double *vel, size_t satellites,
                       size_t knots, size_t samples, size_t phase_rows,
                       const int64_t *index, const double *fraction, const double *rotation,
                       double step, const double *observer, const double *up, double rf,
                       double *f0, double *e0, double *d0, double *f1, double *e1, double *d1)
{
    for (size_t s = 0; s < satellites; ++s) {
        const size_t group = phase_rows == 1 ? 0 : s;
        const double *trig = rotation + group * 6;
        for (size_t t = 0; t < samples; ++t) {
            double p[3][3], v[3][3], dp[3], dv[3];
            for (size_t a = 0; a < 3; ++a) {
                size_t i = (group * 3 + a) * samples + t;
                if (index[i] < 0 || (size_t)index[i] >= knots - 1) return 2;
                size_t k = 3 * (s * knots + (size_t)index[i]);
                rotated(pos + k, fraction[i], trig + 2 * a, p[a]);
                rotated(vel + k, fraction[i], trig + 2 * a, v[a]);
            }
            for (size_t j = 0; j < 3; ++j) {
                dp[j] = (p[1][j] - p[2][j]) / (2 * step);
                dv[j] = (v[1][j] - v[2][j]) / (2 * step);
            }
            size_t q = s * samples + t;
            if (project_observer(p[0], v[0], dp, dv, observer, up, rf, f0 + q, e0 + q, d0 + q) ||
                project_observer(p[0], v[0], dp, dv, observer + 3, up + 3, rf, f1 + q, e1 + q, d1 + q))
                return 1;
        }
    }
    return 0;
}
