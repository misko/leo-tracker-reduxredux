#ifndef LEO_EXPERIMENTAL_REFINE_PARITY_H
#define LEO_EXPERIMENTAL_REFINE_PARITY_H

#include "receiver_refine_batch.h"
#include <stdint.h>

int delay_refine_parity(const float *, const float *, RefineRequest, double, double, double, double [4]);
void experimental_receiver_parity_read(uint64_t [2]);
void experimental_receiver_parity_reset(void);

#endif
