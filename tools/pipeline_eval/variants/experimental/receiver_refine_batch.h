#ifndef LEO_EXPERIMENTAL_REFINE_BATCH_H
#define LEO_EXPERIMENTAL_REFINE_BATCH_H

typedef struct { int epoch; double hz; } RefineRequest;

int delay_refine_bank(const float *, const float *, const RefineRequest *, int,
                      double, double, double (*)[4]);

#endif
