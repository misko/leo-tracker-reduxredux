/* Evaluate the original centered Gaussian contrast and its uniform-orbit mixture. */
#include <math.h>
#include <stdint.h>
#include <stddef.h>

static double logadd(double a, double b) {
    if (a == -INFINITY) return b;
    return fmax(a, b) + log1p(exp(-fabs(a - b)));
}

int regional_track_scores(size_t tracks, size_t orbits, size_t times,
        const int64_t *offset, const int64_t *index, const double *observed,
        const double *scale, const double *baseline, const double *frequency,
        const int8_t *horizon, const double *derivative, double noise,
        double log_catalogue, double *raw, double *phase, double *score, int64_t *owner) {
    for (size_t t = 0; t < tracks; t++) {
        size_t start = offset[t], n = offset[t + 1] - start;
        double best = -INFINITY, mixture = -INFINITY;
        int64_t winner = -1;
        if (n >= 2) for (size_t orbit = 0; orbit < orbits; orbit++) {
            size_t base = orbit * times, j = 0;
            for (; j < n; j++) if (horizon[base + index[start + j]] < 0) break;
            if (j != n) continue;
            double mean_raw = 0., mean_derivative = 0.;
            for (j = 0; j < n; j++) {
                size_t i = base + index[start + j];
                raw[j] = (observed[start + j] - scale[t] * frequency[i]) / noise;
                phase[j] = scale[t] * derivative[i];
                mean_raw += raw[j];
                mean_derivative += phase[j];
            }
            mean_raw /= n;
            mean_derivative /= n;
            double variance = 0., rhs = 0.;
            for (j = 0; j < n; j++) {
                raw[j] -= mean_raw;
                phase[j] = (phase[j] - mean_derivative) / noise;
                variance += phase[j] * phase[j];
                rhs += raw[j] * phase[j];
            }
            variance += 1.;
            double slope = rhs / variance, quadratic = 0.;
            for (j = 0; j < n; j++) {
                double residual = raw[j] - phase[j] * slope;
                quadratic += residual * residual;
            }
            double ratio = baseline[t] - .5 * ((quadratic + slope * slope) + log(variance));
            if (!isfinite(ratio)) return 1;
            if (ratio > best) { best = ratio; winner = orbit; }
            mixture = logadd(mixture, ratio);
        }
        double odds = mixture - log_catalogue;
        score[t] = logadd(odds, 0.);
        owner[t] = odds > 0. ? winner : -1;
    }
    return 0;
}
