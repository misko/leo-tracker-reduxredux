/* The refinement window is nine samples around an epoch modulo one pilot period. */
enum { period = 13333, radius = 4 };

__attribute__((visibility("hidden")))
int leo_pgo_delay_refine(const float *, const float *, int, double, double, double, double *);

__attribute__((visibility("hidden")))
int leo_reference_delay_refine(const float *, const float *, int, double, double, double, double *);

int delay_refine(const float *iq, const float *pilot, int epoch, double hz,
                 double lo, double hi, double *result) {
    if ((epoch >= 0 && epoch < radius) || (epoch >= period - radius && epoch < period))
        return leo_reference_delay_refine(iq, pilot, epoch, hz, lo, hi, result);
    return leo_pgo_delay_refine(iq, pilot, epoch, hz, lo, hi, result);
}
