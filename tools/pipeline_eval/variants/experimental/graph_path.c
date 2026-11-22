/* The release's ordered second-order edge recurrence in binary64. */
#include <stdint.h>
#include <stdlib.h>
#include <float.h>

#if FLT_RADIX != 2 || DBL_MANT_DIG != 53 || FLT_EVAL_METHOD != 0
#error The Graph recurrence requires binary64 evaluation without excess precision.
#endif

typedef struct {
    double score;
    int64_t predecessor;
    int64_t count;
    int64_t start;
    unsigned char allowed;
} EdgeState;

uint32_t leo_graph_path_abi(void) {
    return 1;
}

int64_t leo_graph_path_v1(
    int64_t points, int64_t edges, const double *time,
    const int64_t *source, const int64_t *target, const double *duration,
    const double *velocity, const int64_t *incoming_offset,
    const int64_t *incoming, const int64_t *outgoing_offset,
    const int64_t *outgoing, const unsigned char *available,
    const unsigned char *enabled, double reward, double penalty,
    double variance_scale, int64_t minimum_count, double minimum_span,
    int64_t *path, double *value
) {
    if (!edges) {
        *value = 0.0;
        return 0;
    }
    EdgeState *state = malloc((size_t)edges * sizeof(*state));
    if (!state) {
        return -1;
    }
    for (int64_t i = 0; i < edges; ++i) {
        state[i].allowed = available[source[i]] && available[target[i]] && enabled[i];
    }
    double base = 2.0 * reward - penalty;
    for (int64_t node = 0; node < points; ++node) {
        for (int64_t j = outgoing_offset[node]; j < outgoing_offset[node + 1]; ++j) {
            int64_t next = outgoing[j];
            if (!state[next].allowed) {
                continue;
            }
            double b = duration[next];
            double inv_b2 = 1.0 / (b * b);
            double gap = 0.05 * b;
            double best = base - gap;
            int64_t parent = -1;
            for (int64_t i = incoming_offset[node]; i < incoming_offset[node + 1]; ++i) {
                int64_t prev = incoming[i];
                if (!state[prev].allowed) {
                    continue;
                }
                double a = duration[prev];
                double terms = (1.0 / (a * a) + inv_b2) + 1.0 / (a * b);
                double acceleration = (20.0 * (a + b)) / 2.0;
                double variance = variance_scale * terms + acceleration * acceleration;
                double change = velocity[prev] - velocity[next];
                double transition = (2.0 * (change * change)) / variance;
                double candidate = ((state[prev].score + reward) - gap) - transition;
                /* Ties retain the base or the first edge in NumPy's index order. */
                if (candidate > best) {
                    best = candidate;
                    parent = prev;
                }
            }
            state[next].score = best;
            state[next].predecessor = parent;
            state[next].count = parent < 0 ? 2 : state[parent].count + 1;
            state[next].start = parent < 0 ? node : state[parent].start;
        }
    }
    int64_t last = -1;
    *value = 0.0;
    for (int64_t i = 0; i < edges; ++i) {
        if (state[i].allowed && state[i].count >= minimum_count && state[i].score > *value
                && time[target[i]] - time[state[i].start] >= minimum_span) {
            last = i;
            *value = state[i].score;
        }
    }
    int64_t found = 0;
    while (last >= 0) {
        path[found++] = last;
        last = state[last].predecessor;
    }
    free(state);
    return found;
}
