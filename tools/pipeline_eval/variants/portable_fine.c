/* Standalone folding, absolute rotation, normalized scoring and peak selection. */
#include "portable_fine.h"

#include <math.h>
#include <string.h>

/* The two components use the same binary64 record across translation units. */
void fine_search_twiddles(PortableFineComplex *roots);
void fine_search_transform(
    const PortableFineComplex *weighted, const PortableFineComplex *roots,
    PortableFineComplex *work, PortableFineComplex *selected, int frames, int bins
);

static struct { double step_hz, sample_rate_hz; } const geometry = {500.0, 10000000.0};

void portable_fine_prepare(PortableFineWorkspace *workspace) {
    memset(workspace->scratch, 0, sizeof(workspace->scratch));
    fine_search_twiddles(workspace->roots);
    workspace->rotation_base_hz = NAN;
}

static inline PortableFineComplex multiply(PortableFineComplex a, PortableFineComplex b) {
    return (PortableFineComplex){a.r * b.r - a.i * b.i, a.r * b.i + a.i * b.r};
}

static inline double power(PortableFineComplex z) {
    return z.r * z.r + z.i * z.i;
}

static int supported_grid(unsigned bins, double absolute_hz) {
    const double half_band = geometry.sample_rate_hz / 2;
    return bins >= 2 && bins <= PORTABLE_FINE_MAX_BINS && isfinite(absolute_hz) &&
           absolute_hz >= -half_band && absolute_hz + (bins - 1) * geometry.step_hz <= half_band;
}

int portable_fine_score(
    PortableFineWorkspace *workspace, const PortableFineComplex *samples,
    const PortableFineComplex *frame_template, unsigned epoch, double first_absolute_hz,
    unsigned bins, double *scores, unsigned *frames
) {
    if (epoch >= PORTABLE_FINE_EPOCHS || !supported_grid(bins, first_absolute_hz)) return -1;

    const int fold_stop = 301 * PORTABLE_FINE_TAPS;
    const int fold_stride = 2 * PORTABLE_FINE_TAPS;
    const double negative_turn = -6.283185307179586476925286766559005768;
    if (workspace->rotation_base_hz != first_absolute_hz) {
        for (int symbol = fold_stride, j = 0; symbol < fold_stop; symbol += fold_stride) {
            for (int i = 0; i < PORTABLE_FINE_TAPS; ++i, ++j) {
                double angle = negative_turn * first_absolute_hz * (symbol + i)
                               / geometry.sample_rate_hz;
                workspace->rotation[j] = (PortableFineComplex){cos(angle), sin(angle)};
            }
        }
        workspace->rotation_base_hz = first_absolute_hz;
    }

    double template_power = 0;
    for (int symbol = fold_stride; symbol < fold_stop; symbol += fold_stride) {
        for (int i = 0; i < PORTABLE_FINE_TAPS; ++i) template_power += power(frame_template[symbol + i]);
    }
    if (!isfinite(template_power)) return -1;

    *frames = 0;
    for (unsigned k = 0; k < bins; ++k) scores[k] = 0;
    for (unsigned frame = 0; frame < 15; ++frame) {
        /* Round frame * 10,000,000 / 750 to the nearest sample. */
        unsigned start = epoch + (frame * 40000 + 1) / 3;
        if (start + fold_stop > PORTABLE_FINE_SAMPLES) break;
        ++*frames;
        double received_power = 0;
        for (int symbol = fold_stride, j = 0; symbol < fold_stop; symbol += fold_stride) {
            for (int i = 0; i < PORTABLE_FINE_TAPS; ++i, ++j) {
                PortableFineComplex received = samples[start + symbol + i];
                PortableFineComplex reference = frame_template[symbol + i];
                reference.i = -reference.i;
                received_power += power(received);
                workspace->folded[j] = multiply(multiply(received, reference), workspace->rotation[j]);
            }
        }
        double energy_product = received_power * template_power;
        if (!isfinite(energy_product)) return -1;
        if (energy_product == 0) continue;
        fine_search_transform(workspace->folded, workspace->roots, workspace->scratch,
                              workspace->selected, 1, (int)bins);
        double denominator = sqrt(energy_product);
        for (unsigned k = 0; k < bins; ++k) scores[k] += sqrt(power(workspace->selected[k])) / denominator;
    }
    for (unsigned k = 0; k < bins; ++k) scores[k] /= *frames;
    return 0;
}

static inline double frequency(double first, unsigned k) {
    return first + k * geometry.step_hz;
}

static int better(const double *scores, double first, unsigned a, unsigned b) {
    if (scores[a] != scores[b]) return scores[a] > scores[b];
    double af = frequency(first, a), bf = frequency(first, b);
    return fabs(af) == fabs(bf) ? af < bf : fabs(af) < fabs(bf);
}

int portable_fine_peak(const double *scores, double first, unsigned bins, PortableFinePeak *peak) {
    if (!supported_grid(bins, first)) return -1;
    for (unsigned k = 0; k < bins; ++k) if (!isfinite(scores[k])) return -1;

    unsigned winner = 0, runner = 1;
    if (better(scores, first, 1, 0)) { winner = 1; runner = 0; }
    for (unsigned k = 2; k < bins; ++k) {
        if (better(scores, first, k, winner)) { runner = winner; winner = k; }
        else if (better(scores, first, k, runner)) runner = k;
    }

    const double error = PORTABLE_FINE_SCORE_TOLERANCE;
    peak->winner = winner;
    peak->runner = runner;
    peak->gap = scores[winner] - scores[runner];
    peak->guard = peak->gap <= 2 * error ? PORTABLE_FINE_CLOSE_RANK : 0;
    peak->interpolated_hz = frequency(first, winner);
    peak->curvature = 0;
    if (winner == 0 || winner + 1 == bins) return 0;

    double left = scores[winner - 1], right = scores[winner + 1];
    double curvature = left - 2 * scores[winner] + right;
    peak->curvature = curvature;
    if (curvature >= -1e-15) {
        peak->guard |= PORTABLE_FINE_UNSTABLE_INTERPOLATION;
        return 0;
    }
    double offset = 0.5 * (left - right) / curvature;
    peak->interpolated_hz += fmin(1.0, fmax(-1.0, offset)) * geometry.step_hz;
    double stable = -curvature - 4 * error;
    if (stable <= 0 || geometry.step_hz * (error + 4 * error * fabs(offset)) / stable >
                       PORTABLE_FINE_INTERPOLATION_TOLERANCE_HZ) {
        peak->guard |= PORTABLE_FINE_UNSTABLE_INTERPOLATION;
    }
    return 0;
}
