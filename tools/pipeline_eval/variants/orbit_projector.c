/* Project interpolated ECEF states onto a stationary receiver. Units are km and s. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

static void rotated(const double *x, double fraction, const double *trig, double out[3])
{
    double a = x[0] + fraction * (x[3] - x[0]);
    double b = x[1] + fraction * (x[4] - x[1]);
    out[0] = trig[0] * a - trig[1] * b;
    out[1] = trig[1] * a + trig[0] * b;
    out[2] = x[2] + fraction * (x[5] - x[2]);
}

int project_orbit_grid(const double *pos, const double *vel, size_t satellites,
                       size_t knots, size_t samples, size_t phase_rows,
                       const int64_t *index, const double *fraction, const double *rotation,
                       double step, const double *observer, const double *up, double rf,
                       double *frequency, double *elevation_sine, double *derivative)
{
    for (size_t s = 0; s < satellites; ++s) {
        const size_t group = phase_rows == 1 ? 0 : s;
        const double *trig = rotation + group * 6;
        for (size_t t = 0; t < samples; ++t) {
            double p[3][3], v[3][3];
            for (size_t a = 0; a < 3; ++a) {
                size_t i = (group * 3 + a) * samples + t;
                if (index[i] < 0 || (size_t)index[i] >= knots-1) return 2;
                size_t k = 3 * (s * knots + (size_t)index[i]);
                rotated(pos + k, fraction[i], trig + 2*a, p[a]);
                rotated(vel + k, fraction[i], trig + 2*a, v[a]);
            }
            double squared_range = 0, radial = 0, vertical = 0;
            double radial_change = 0, squared_range_half_change = 0;
            for (size_t j = 0; j < 3; ++j) {
                double delta = p[0][j] - observer[j];
                double dp = (p[1][j] - p[2][j]) / (2*step);
                double dv = (v[1][j] - v[2][j]) / (2*step);
                squared_range += delta * delta;
                radial += delta * v[0][j];
                vertical += delta * up[j];
                radial_change += dp * v[0][j] + delta * dv;
                squared_range_half_change += delta * dp;
            }
            double range = sqrt(squared_range);
            if (!(range > 0) || !isfinite(range)) return 1;
            size_t dest = s*samples + t;
            frequency[dest] = -rf * (radial / range) / 299792.458;
            elevation_sine[dest] = vertical / range;
            derivative[dest] = -rf * (radial_change / range -
                                      radial * squared_range_half_change / (range*squared_range)) / 299792.458;
        }
    }
    return 0;
}
