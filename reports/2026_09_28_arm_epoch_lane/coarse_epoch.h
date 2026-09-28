#ifndef LEO_RESEARCH_COARSE_EPOCH_H
#define LEO_RESEARCH_COARSE_EPOCH_H

/* Four adjacent epochs for all twelve CFOs. `sum` addresses CFO zero of the
 * first epoch and retains the native epoch-major stride of twelve. */
void leo_coarse_epoch4_add(const float *samples, const float *real,
    const float *imag, int taps, const float inverse_norm[4], float *sum);

#endif
