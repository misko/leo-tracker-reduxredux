#ifndef LEO_PORTABLE_COARSE_H
#define LEO_PORTABLE_COARSE_H

#include <stddef.h>
#include <stdint.h>
#include "portable_verifier.h"

enum {
    PORTABLE_COARSE_LOWER = 0,
    PORTABLE_COARSE_UPPER = 1,
    PORTABLE_COARSE_PRIMARY = 12,
    PORTABLE_COARSE_RETRY = 22,
    PORTABLE_COARSE_MAX_LANES = 21
};

typedef struct PortableCoarse PortableCoarse;
typedef struct {
    unsigned samples, edge, lane_mask;
    double center_hz[2], low_hz, high_hz;
} PortableCoarseCapture;

typedef struct {
    double score, residual_hz;
    unsigned original_epoch, refined_epoch, cfo_lane;
} PortableCoarsePeak;

/* The context owns both published, fixed-rate templates and scratch. */
PortableCoarse *portable_coarse_create(unsigned edge);
void portable_coarse_free(PortableCoarse *workspace);
size_t portable_coarse_workspace_bytes(void);
const PortableFineComplex *portable_coarse_template(const PortableCoarse *workspace,
                                                   unsigned control);

/* IQ layout is [sample][physical lane][I,Q]. Seed order is the historical coarse order.
 * Both output arrays have capacity PORTABLE_VERIFIER_MAX_SEEDS. peaks may be NULL. */
int portable_coarse_acquire(PortableCoarse *workspace, const int16_t *stereo_iq,
                            const PortableCoarseCapture *capture, unsigned lane, unsigned anchors,
                            PortableVerifierSeed *seeds, PortableCoarsePeak *peaks,
                            unsigned *count);

/* Read-only diagnostic map and support from the most recent acquired physical lane. */
const double *portable_coarse_scores(const PortableCoarse *workspace, unsigned *lanes);
const uint16_t *portable_coarse_support(const PortableCoarse *workspace);

/* The original fixed Standard peak selector. eligible has lanes * epochs bytes. */
unsigned portable_coarse_select(const double *grid, const double *residual_hz, unsigned lanes,
                                unsigned epochs, uint8_t *eligible, PortableCoarsePeak *peaks);

#endif
