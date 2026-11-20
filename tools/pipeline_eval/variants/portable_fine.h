#ifndef LEO_PORTABLE_FINE_H
#define LEO_PORTABLE_FINE_H

/* Fixed 10 MS/s capture geometry. Inputs and scratch are caller-owned. */
enum {
    PORTABLE_FINE_SAMPLES = 200000,
    PORTABLE_FINE_EPOCHS = 13333,
    PORTABLE_FINE_TAPS = 44,
    PORTABLE_FINE_PILOTS = 150 * PORTABLE_FINE_TAPS,
    PORTABLE_FINE_FFT = 20000,
    PORTABLE_FINE_MAX_BINS = 321,
    PORTABLE_FINE_CLOSE_RANK = 1,
    PORTABLE_FINE_UNSTABLE_INTERPOLATION = 2
};

#define PORTABLE_FINE_SCORE_TOLERANCE 5e-13
#define PORTABLE_FINE_INTERPOLATION_TOLERANCE_HZ 1e-6

typedef struct { double r, i; } PortableFineComplex;

typedef struct {
    PortableFineComplex roots[PORTABLE_FINE_FFT];
    PortableFineComplex scratch[2 * PORTABLE_FINE_FFT];
    PortableFineComplex folded[PORTABLE_FINE_PILOTS];
    PortableFineComplex rotation[PORTABLE_FINE_PILOTS];
    PortableFineComplex selected[PORTABLE_FINE_MAX_BINS];
    double rotation_base_hz;
} PortableFineWorkspace;

typedef struct {
    unsigned winner, runner, guard, frames;
    double interpolated_hz, gap, curvature;
} PortableFinePeak;

void portable_fine_prepare(PortableFineWorkspace *workspace);

/* Score a 500 Hz grid at one epoch using full complex samples (typically converted CI16)
 * and one capture producer frame template. Return 0 on success; -1 on unsupported input.
 * Consumers needing a stable peak use the guard from portable_fine_peak before accepting it. */
int portable_fine_score(
    PortableFineWorkspace *workspace, const PortableFineComplex *samples,
    const PortableFineComplex *frame_template, unsigned epoch, double first_absolute_hz,
    unsigned bins, double *scores, unsigned *frames
);

/* Rank by (score, -abs(residual CFO), -residual CFO) and fit the original parabolic peak. */
int portable_fine_peak(
    const double *scores, double first_residual_hz, unsigned bins, PortableFinePeak *peak
);

#endif
