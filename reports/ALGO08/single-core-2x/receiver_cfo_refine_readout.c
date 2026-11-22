/* Forward the original native calls and record their boundary values for one scout. */
#include <string.h>
#include "receiver_refine_batch.h"

enum { capacity = 16 };
typedef int (*Decimate)(const float *, const float *, int, int, float *);
typedef int (*Refine)(const float *, const float *, int, double, double, double, double *);
typedef int (*Bank)(const float *, const float *, const RefineRequest *, int, double, double,
                    double (*)[4]);

typedef struct {
    const float *iq, *pilot, *fir_output;
    int bank_count, bank_calls, scalar_count;
    RefineRequest seeds[capacity], scalar[capacity];
    double results[capacity][4];
} RefineReadout;

static Decimate original_decimate;
static Refine original_refine;
static Bank original_bank;
static RefineReadout *readout;

void cfo_refine_readout_setup(Decimate decimate, Refine refine, Bank bank, RefineReadout *out) {
    original_decimate = decimate;
    original_refine = refine;
    original_bank = bank;
    readout = out;
}

int delay_decimate(const float *x, const float *coeff, int taps, int stride, float *out) {
    int status = original_decimate(x, coeff, taps, stride, out);
    if (!status && readout && stride == 4) readout->fir_output = out;
    return status;
}

int delay_refine(const float *x, const float *h, int epoch, double hz, double lo, double hi,
                 double *out) {
    if (readout && readout->scalar_count < capacity) {
        readout->scalar[readout->scalar_count++] = (RefineRequest){epoch, hz};
    }
    return original_refine(x, h, epoch, hz, lo, hi, out);
}

int delay_refine_bank(const float *x, const float *h, const RefineRequest *seeds, int n,
                      double lo, double hi, double (*out)[4]) {
    int status = original_bank(x, h, seeds, n, lo, hi, out);
    if (!status && readout && n >= 0 && n <= capacity) {
        readout->bank_count = n;
        ++readout->bank_calls;
        readout->iq = x;
        readout->pilot = h;
        memcpy(readout->seeds, seeds, n * sizeof(*seeds));
        memcpy(readout->results, out, n * sizeof(*out));
    }
    return status;
}
