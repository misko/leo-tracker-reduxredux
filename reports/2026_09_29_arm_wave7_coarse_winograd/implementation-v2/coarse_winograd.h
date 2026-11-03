#ifndef COARSE_WINOGRAD_H
#define COARSE_WINOGRAD_H

#include <stddef.h>

#define CW_CFO 12

typedef struct { float re[6][CW_CFO], im[6][CW_CFO]; } cw_filters;

void cw_prepare(const float h_re[3][CW_CFO], const float h_im[3][CW_CFO],
    cw_filters *out);
void cw_four(const float x_re[6], const float x_im[6], const cw_filters *filters,
    float y_re[4][CW_CFO], float y_im[4][CW_CFO]);
void cw_direct(const float x_re[6], const float x_im[6],
    const float h_re[3][CW_CFO], const float h_im[3][CW_CFO],
    float y_re[4][CW_CFO], float y_im[4][CW_CFO]);

#endif
