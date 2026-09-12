#ifndef LEO_DECISION_DECIMATOR_H
#define LEO_DECISION_DECIMATOR_H
#include <stddef.h>
#include <stdint.h>

/* Research candidate, not a published wire contract. Q15 symmetric causal FIRs,
 * round ties toward +infinity and saturate at each stage. Input/output are one
 * RX CI16; every call resets history. Setup allocates bounded heap scratch.
 * Optional ARM FP32 kernel uses bounded stack scratch and approximate sums;
 * its output tolerance must be qualified against the exact integer reference.
 * n1=0 selects direct factor-four; otherwise both stages decimate by two.
 * Coefficient absolute sum must be <65536 to guarantee int32 accumulation. */
typedef struct leo_decimator leo_decimator;
leo_decimator *leo_decimator_create(const int16_t *h1, unsigned n1,
    const int16_t *h2, unsigned n2, size_t count);
/* Research polyphase recursive candidate: Q15 first stage, Q14 non-symmetric
 * numerator, then four stable all-pole sections at the output rate. No constant
 * group-delay claim applies. History resets at each run, including recursive
 * state. Denominator pairs describe 1+a1*z^-1+a2*z^-2. */
leo_decimator *leo_decimator_create_recursive(const int16_t *h1, unsigned n1,
    const int16_t *numerator, unsigned n2, const float denominator[8], size_t count);
void leo_decimator_destroy(leo_decimator *w);
int leo_decimator_run(leo_decimator *w, const int16_t *iq, size_t count,
    int16_t *output);
#endif
