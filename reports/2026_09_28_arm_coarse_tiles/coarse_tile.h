#ifndef LEO_RESEARCH_COARSE_TILE_H
#define LEO_RESEARCH_COARSE_TILE_H

/* Four adjacent epochs by four CFOs per block. `sum` addresses CFO zero of
 * the first epoch and retains the native epoch-major stride of twelve. */
void leo_coarse_tile4_add(const float *samples,const float *real,
    const float *imag,int taps,const float inverse_norm[4],float *sum);

#endif
