#ifndef LEO_PORTABLE_VERIFIER_H
#define LEO_PORTABLE_VERIFIER_H

#include <stddef.h>
#include <stdint.h>
#include "portable_fine.h"

enum {
    PORTABLE_VERIFIER_MAX_SEEDS = 8,
    PORTABLE_VERIFIER_CONDITIONED_BINS = 42,
    PORTABLE_VERIFIER_INTEGER_GATE = 1,
    PORTABLE_VERIFIER_FRACTIONAL_GATE = 2,
    PORTABLE_VERIFIER_FRACTIONAL_COMPLETE = 4,
    PORTABLE_VERIFIER_FINE_GUARD = 8,
    PORTABLE_VERIFIER_CONDITIONED_TIE = 16,
    PORTABLE_VERIFIER_GLRT_BIN_TIE = 32,
    PORTABLE_VERIFIER_GATE_GUARD = 64,
    PORTABLE_VERIFIER_ACQUISITION_EQUIVALENT_TIE = 128
};

typedef struct PortableVerifier PortableVerifier;

typedef struct {
    unsigned epoch, bins;
    double absolute_hz, residual_hz;
} PortableVerifierSeed;

typedef struct {
    unsigned seed_index, fine_winner, conditioned_winner, conditioned_bins, flags, stage_frames;
    double fine_residual_hz, acquired_hz, acquired_residual_hz;
    double acquire, verify, verify_control, conditioned;
    double integer_exact, integer_control, integer_residual_hz;
    double offset_samples, curvature, fractional_exact, fractional_control, fractional_residual_hz;
    double exact_grid[5], control_grid[5];
    double conditioned_grid[PORTABLE_VERIFIER_CONDITIONED_BINS];
    double conditioned_scores[PORTABLE_VERIFIER_CONDITIONED_BINS];
} PortableVerifierResult;

/* Templates are supplied by the caller from the bound pilot edge and symbol roll. */
PortableVerifier *portable_verifier_create(const PortableFineComplex *exact,
                                          const PortableFineComplex *control);
void portable_verifier_free(PortableVerifier *workspace);
size_t portable_verifier_workspace_bytes(void);

/* Buffer geometry is [200,000 complex samples][2 physical lanes][I,Q]. */
int portable_verifier_load(PortableVerifier *workspace, const int16_t *stereo_iq, unsigned lane);

/* Input order is the original coarse seed order; output is sorted by acquisition evidence. */
int portable_verifier_acquire(PortableVerifier *workspace, const PortableVerifierSeed *seeds,
                              unsigned count, double center_hz, double low_hz, double high_hz,
                              PortableVerifierResult *results);
int portable_verifier_glrt(PortableVerifier *workspace, unsigned epoch, PortableVerifierResult *result);
int portable_verifier_fractional_peak(const double *scores, double *offset, double *curvature);

#endif
