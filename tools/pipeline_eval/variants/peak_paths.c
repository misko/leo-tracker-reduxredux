#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#define ALIAS_HZ (1.0 / 4.4e-6)
#define FLOOR_SCORE (-1e90)

static double fold(double value) {
    return value - ALIAS_HZ * nearbyint(value / ALIAS_HZ);
}

/* The zero-score state is background. Each active state stores one predecessor.
   Beginning again is legal at each visit and a bridge lasts at most 2.6 seconds. */
int peak_paths_decode(int orbits, int visits, int peaks, int fixed,
                      const double *time, const double *cfo, const double *emission,
                      const double *predicted, double *scores, int16_t *paths) {
    const int size = visits * peaks;
    double *scores_at_peak = malloc((size_t)size * sizeof(double));
    double *level = malloc((size_t)size * sizeof(double));
    double *residual = malloc((size_t)size * sizeof(double));
    int *parent = malloc((size_t)size * sizeof(int));
    if (!scores_at_peak || !level || !residual || !parent) {
        free(scores_at_peak); free(level); free(residual); free(parent);
        return -1;
    }
    for (int orbit = 0; orbit < orbits; ++orbit) {
        const double *frequency = predicted + orbit * visits;
        int16_t *path = paths + orbit * visits;
        int last = -1;
        double best = 0.0;
        for (int t = 0; t < visits; ++t) {
            path[t] = -1;
            for (int k = 0; k < peaks; ++k) {
                int state = t * peaks + k;
                scores_at_peak[state] = FLOOR_SCORE;
                if (!isfinite(frequency[t]) || !isfinite(emission[state])) continue;
                double observed = fold(cfo[state] - frequency[t]);
                residual[state] = observed;
                if (fixed && fabs(observed) > 1400.0) continue;
                double birth = fixed ? 3.0 : 8.0;
                double evidence = emission[state];
                if (fixed) evidence -= 0.5 * pow(observed / 450.0, 2.0);
                double value = evidence - birth;
                double bias = observed;
                int chosen = -1;
                for (int gap = 1; gap <= 9 && gap <= t; ++gap) {
                    double span = time[t] - time[t-gap];
                    if (span <= 0.0 || span > 2.6) break;
                    double step_scale = 390.0 + 190.0 * span;
                    for (int j = 0; j < peaks; ++j) {
                        int before = (t-gap)*peaks + j;
                        if (scores_at_peak[before] <= FLOOR_SCORE) continue;
                        double slope = fold(observed-residual[before]) / step_scale;
                        double delta = fold(observed-level[before]);
                        if (fabs(slope) > 5.0 || fabs(delta) > 6500.0) continue;
                        double penalty = 0.5*slope*slope + 0.5*pow(delta / 2200.0, 2.0);
                        double next = scores_at_peak[before] + evidence + 0.9
                                      - penalty - 0.35*(gap - 1);
                        if (next > value) {
                            value = next;
                            chosen = before;
                            bias = fold(level[before] + 0.06*delta);
                        }
                    }
                }
                scores_at_peak[state] = value;
                level[state] = bias;
                parent[state] = chosen;
                if (value > best) {
                    best = value;
                    last = state;
                }
            }
        }
        scores[orbit] = best;
        for (; last != -1; last = parent[last]) {
            path[last / peaks] = (int16_t)(last % peaks);
        }
    }
    free(scores_at_peak); free(level); free(residual); free(parent);
    return 0;
}
