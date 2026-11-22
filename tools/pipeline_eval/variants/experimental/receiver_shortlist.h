#ifndef LEO_EXPERIMENTAL_RECEIVER_SHORTLIST_H
#define LEO_EXPERIMENTAL_RECEIVER_SHORTLIST_H

#include "timing_first_receiver.h"

enum { audit_seeds = 24 };
typedef struct { double epoch, hz; int rank, confirmed; } AuditPeak;
typedef struct {
    double epoch, hz;
    int timing_cell_rank, timing_seed_rank, frequency_cell_rank, seeds_used;
    int coarse_rank, refined_rank, confirmed_rank, verified_rank;
    int candidates, first_confirmed;
    AuditPeak peaks[audit_seeds];
} ShortlistAudit;

typedef struct { int epoch; double hz; TimingFirstResult raw; } SecondSeed;
typedef struct { unsigned first_confirmed, narrow_trials, local_confirmed, full_residual, full_retry; } ShortlistFast;

int timing_shortlist_audit(TimingFirst *, const int16_t *, int, double, double, ShortlistAudit *);
int timing_shortlist_pair(TimingFirst *, const int16_t *, int, double, double,
                          TimingFirstResult *, SecondSeed *, int *);
int timing_shortlist_residual(TimingFirst *, const int16_t *, int, double, double,
                              SecondSeed, TimingFirstResult *);

#endif
