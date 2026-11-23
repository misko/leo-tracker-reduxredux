/* Dense prepared phase tangent for the ALGO08 geographic mixture proof. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

static inline double dot(const double *v, const double *reference)
{
    return (v[0] * reference[0] + v[1] * reference[1]) + v[2] * reference[2];
}

int dense_geographic_projection(
    size_t cells, const double *restrict position, const double *restrict velocity,
    const double *restrict dp, const double *restrict dv,
    const double *restrict squared_norm, const double *restrict pv,
    const double *restrict derivative_numerator, const double *restrict position_dot_derivative,
    const double *observer, double observer_squared, const double *up, double observer_up,
    double rf, double *restrict frequency, int8_t *restrict horizon, double *restrict derivative)
{
    int invalid = 0;
    const double light = 299792.458;
    #pragma omp simd reduction(|:invalid)
    for (size_t cell = 0; cell < cells; ++cell) {
        const size_t index = 3 * cell;
        const double *p = position + index;
        const double range = sqrt((squared_norm[cell] - 2 * dot(p, observer)) + observer_squared);
        const double numerator = pv[cell] - dot(velocity + index, observer);
        const double num_change = derivative_numerator[cell] - dot(dv + index, observer);
        const double range_change = position_dot_derivative[cell] - dot(dp + index, observer);
        const double vertical = (dot(p, up) - observer_up) / range;
        const double rate = numerator / range;
        const double tangent = num_change / range - numerator * range_change / ((range * range) * range);

        frequency[cell] = (-rf * rate) / light;
        derivative[cell] = (-rf * tangent) / light;
        horizon[cell] = vertical >= 0 ? 1 : -1;
        invalid |= !(range > 0 && isfinite(range) && isfinite(rate) && isfinite(tangent) && isfinite(vertical));
    }
    return invalid;
}
