#ifndef LEO_RESEARCH_CONDITIONED_CZT_H
#define LEO_RESEARCH_CONDITIONED_CZT_H

#include <stddef.h>

/* Compute magnitudes at f0 + j*100 Hz from interleaved FP32 samples already
 * modulated by f0. Returns zero on success; callers must retain their exact
 * per-bin implementation as the fallback for every nonzero return. */
int leo_conditioned_czt_magnitudes(const float *weighted, size_t n,
    double rate, int nf, float *magnitudes);

#endif
