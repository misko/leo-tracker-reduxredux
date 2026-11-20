/* Stream one site's folded residuals. Each orbit and RF group fits one circular
 * offset using training bins. A vote counts at most once per time bin. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define PERIOD (1.0 / 4.4e-6)
#define LIGHT_KM_S 299792.458
#define SIN_ELEVATION 0.3420201433256687
#define MAX_MATCHES 64

typedef struct { double t, rf, cfo; int group, bin; } Point;
typedef struct { double x, y, z, min_dot; } Cap;
typedef struct { double hz_per_hz, sin_elevation; } Look;
typedef struct { int last, train, held; } Vote;
typedef struct {
    int orbit, group, train, held;
    double offset_hz, train_score, held_score, held_expected;
} Match;

static void retain(Match *out, size_t *used, Match candidate)
{
    size_t index = *used;
    if (index == MAX_MATCHES) {
        --index;
        if (candidate.train_score <= out[index].train_score) return;
    } else ++*used;
    for (; index && out[index-1].train_score < candidate.train_score; --index)
        out[index] = out[index-1];
    out[index] = candidate;
}

static double dot(const double *left, const double *right)
{
    return left[0]*right[0] + left[1]*right[1] + left[2]*right[2];
}

int folded_doppler_site(const double *states, const Cap *caps, size_t orbit_count,
    size_t knot_count, double knot_step, const Point *points, size_t point_count,
    size_t group_count, size_t bin_count, int offsets, const double *site,
    const double *up, Match *out)
{
    const double inverse_step = 1.0 / knot_step;
    const double offset_step = PERIOD / offsets;
    const double direction_norm = sqrt(dot(site, site));
    const size_t slots = group_count * (size_t)offsets;
    const size_t counts_size = group_count * bin_count;
    Look *look = malloc(knot_count * sizeof(*look));
    Vote *histogram = malloc(slots * sizeof(*histogram));
    unsigned short *counts = malloc(counts_size * sizeof(*counts));
    if (!look || !histogram || !counts) {
        free(look); free(histogram); free(counts);
        return -1;
    }
    size_t used = 0;
    for (size_t orbit = 0; orbit < orbit_count; ++orbit) {
        Cap cap = caps[orbit];
        if ((cap.x*site[0] + cap.y*site[1] + cap.z*site[2]) < cap.min_dot*direction_norm)
            continue;
        size_t first = knot_count, last = 0;
        for (size_t k = 0; k < knot_count; ++k) {
            const double *state = states + 6*(orbit*knot_count + k);
            double dx[3] = {state[0]-site[0], state[1]-site[1], state[2]-site[2]};
            double inv_range = 1.0 / sqrt(dot(dx, dx));
            look[k].sin_elevation = dot(dx, up)*inv_range;
            look[k].hz_per_hz = -dot(dx, state+3)*inv_range/LIGHT_KM_S;
            if (look[k].sin_elevation >= SIN_ELEVATION) {
                if (first == knot_count) first = k;
                last = k;
            }
        }
        if (first == knot_count || (last-first)*knot_step < 14) continue;
        for (size_t j = 0; j < slots; ++j) histogram[j] = (Vote){ .last=-1 };
        memset(counts, 0, counts_size * sizeof(*counts));
        double earliest = first ? (first-1)*knot_step : 0;
        double latest = (last+1)*knot_step;
        size_t low = 0, high = point_count;
        while (low < high) {
            size_t middle = (low + high)/2;
            if (points[middle].t < earliest) low = middle+1;
            else high = middle;
        }
        for (size_t i = low; i < point_count && points[i].t < latest; ++i) {
            const Point p = points[i];
            const double knot = p.t*inverse_step;
            const size_t k = (size_t)knot;
            if (k+1 >= knot_count) break;
            const double fraction = knot-k;
            const double elevation = look[k].sin_elevation*(1.0-fraction)
                + look[k+1].sin_elevation*fraction;
            if (elevation < SIN_ELEVATION) continue;
            const double doppler = p.rf*(look[k].hz_per_hz*(1.0-fraction)
                + look[k+1].hz_per_hz*fraction);
            const int offset = (int)floor((p.cfo-doppler)/offset_step);
            ++counts[(size_t)p.group*bin_count + p.bin];
            for (int neighbor = 0; neighbor < 2; ++neighbor) {
                Vote *vote = histogram + (size_t)p.group*offsets + ((offset+neighbor)&(offsets-1));
                if (vote->last == p.bin) continue;
                vote->last = p.bin;
                if (p.bin%3 == 2) ++vote->held;
                else ++vote->train;
            }
        }
        for (size_t g = 0; g < group_count; ++g) {
            const Vote *offsets_for_group = histogram + g*offsets;
            int best = 0;
            for (int cell = 1; cell < offsets; ++cell)
                if (offsets_for_group[cell].train > offsets_for_group[best].train) best = cell;
            const Vote vote = offsets_for_group[best];
            if (vote.train < 5) continue;
            double expected[2] = {0}, variance[2] = {1, 1};
            for (size_t b = 0; b < bin_count; ++b) {
                unsigned short n = counts[g*bin_count + b];
                if (!n) continue;
                const double p = 1.0 - pow(1.0-2.0/offsets, n);
                int side = b%3 == 2;
                expected[side] += p;
                variance[side] += p*(1.0-p);
            }
            const double training = (vote.train-expected[0])/sqrt(variance[0]);
            if (training < 2.0) continue;
            const double validation = (vote.held-expected[1])/sqrt(variance[1]);
            const double bias = offset_step*(best < offsets/2 ? best : best-offsets);
            retain(out, &used, (Match){orbit, (int)g, vote.train, vote.held, bias,
                training, validation, expected[1]});
        }
    }
    free(counts); free(histogram); free(look);
    return (int)used;
}
