/* Stream one orbit through an ordered block of bilateral regional probes. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

#define WIDTH 4

static double dot(const double *v, const double (*frame)[WIDTH], size_t field, size_t lane)
{
    return (v[0] * frame[field][lane] + v[1] * frame[field + 1][lane])
           + v[2] * frame[field + 2][lane];
}

static double logadd(double a, double b)
{
    if (a == -INFINITY) return b;
    return fmax(a, b) + log1p(exp(-fabs(a - b)));
}

int regional_probe_block(
    size_t lanes, size_t tracks, size_t orbits, size_t times,
    const double (*frame)[WIDTH], const double *restrict position,
    const double *restrict velocity, const double *restrict dp, const double *restrict dv,
    const double *restrict squared_norm, const double *restrict pv,
    const double *restrict derivative_numerator, const double *restrict position_dot_derivative,
    const int64_t *offset, const int64_t *index, const double *observed,
    const double *scale, const double *baseline, double noise, double log_catalogue,
    double (*restrict frequency)[WIDTH], int8_t (*restrict horizon)[WIDTH],
    double (*restrict derivative)[WIDTH], double *raw, double *phase,
    double (*best)[WIDTH], double (*score)[WIDTH], int64_t (*owner)[WIDTH])
{
    if (!lanes || lanes > WIDTH) return 1;
    for (size_t t = 0; t < tracks; ++t) {
        for (size_t lane = 0; lane < lanes; ++lane) {
            best[t][lane] = score[t][lane] = -INFINITY;
            owner[t][lane] = -1;
        }
    }

    for (size_t orbit = 0; orbit < orbits; ++orbit) {
        int invalid = 0;
        const size_t first = orbit * times;
        for (size_t k = 0; k < times; ++k) {
            const size_t cell = first + k, i = 3 * cell;
            const double *p = position + i;
            #pragma omp simd reduction(|:invalid)
            for (size_t lane = 0; lane < lanes; ++lane) {
                double range = sqrt((squared_norm[cell] - 2 * dot(p, frame, 0, lane))
                                    + frame[6][lane]);
                double numerator = pv[cell] - dot(velocity + i, frame, 0, lane);
                double num_change = derivative_numerator[cell] - dot(dv + i, frame, 0, lane);
                double range_change = position_dot_derivative[cell] - dot(dp + i, frame, 0, lane);
                double vertical = (dot(p, frame, 3, lane) - frame[7][lane]) / range;
                double rate = numerator / range;
                double tangent = num_change / range
                                 - numerator * range_change / ((range * range) * range);
                frequency[k][lane] = (-11.5e9 * rate) / 299792.458;
                derivative[k][lane] = (-11.5e9 * tangent) / 299792.458;
                horizon[k][lane] = vertical >= 0 ? 1 : -1;
                invalid |= !(range > 0 && isfinite(range) && isfinite(rate)
                             && isfinite(tangent) && isfinite(vertical));
            }
        }
        if (invalid) return 1;

        for (size_t t = 0; t < tracks; ++t) {
            size_t start = offset[t], n = offset[t + 1] - start;
            if (n < 2) continue;
            for (size_t lane = 0; lane < lanes; ++lane) {
                size_t j = 0;
                for (; j < n; ++j) if (horizon[index[start + j]][lane] < 0) break;
                if (j != n) continue;
                double mean_raw = 0., mean_derivative = 0.;
                for (j = 0; j < n; ++j) {
                    const size_t k = index[start + j];
                    raw[j] = (observed[start + j] - scale[t] * frequency[k][lane]) / noise;
                    phase[j] = scale[t] * derivative[k][lane];
                    mean_raw += raw[j];
                    mean_derivative += phase[j];
                }
                mean_raw /= n;
                mean_derivative /= n;
                double variance = 0., rhs = 0.;
                for (j = 0; j < n; ++j) {
                    raw[j] -= mean_raw;
                    phase[j] = (phase[j] - mean_derivative) / noise;
                    variance += phase[j] * phase[j];
                    rhs += raw[j] * phase[j];
                }
                variance += 1.;
                double slope = rhs / variance, quadratic = 0.;
                for (j = 0; j < n; ++j) {
                    double residual = raw[j] - phase[j] * slope;
                    quadratic += residual * residual;
                }
                double ratio = baseline[t] - .5 * ((quadratic + slope * slope) + log(variance));
                if (!isfinite(ratio)) return 1;
                if (ratio > best[t][lane]) {
                    best[t][lane] = ratio;
                    owner[t][lane] = orbit;
                }
                score[t][lane] = logadd(score[t][lane], ratio);
            }
        }
    }

    for (size_t t = 0; t < tracks; ++t) {
        for (size_t lane = 0; lane < lanes; ++lane) {
            double odds = score[t][lane] - log_catalogue;
            score[t][lane] = logadd(odds, 0.);
            if (!(odds > 0.)) owner[t][lane] = -1;
        }
    }
    return 0;
}
