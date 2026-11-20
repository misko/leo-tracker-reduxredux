#ifndef LEO_NATIVE_PRUNING_H
#define LEO_NATIVE_PRUNING_H

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Exactly the established regional path can use this without widening the
 * reader aperture. Active epochs are strictly ordered by construction. */
static inline int leo_pruning_valid(const int *epochs, int count, int n)
{
    if (count < 0 || count > 15 || (count > 0 && epochs == NULL)) return 0;
    int previous = -1;
    for (int i = 0; i < count; ++i) {
        if (epochs[i] <= previous || epochs[i] >= n) return 0;
        previous = epochs[i];
    }
    return 1;
}

static inline void leo_pruning_clear(float *sums, int32_t *support, size_t stride,
    const int *epochs, int count)
{
    for (int i = 0; i < count; ++i) {
        int epoch = epochs[i];
        memset(sums + stride * (size_t)epoch, 0, stride * sizeof(*sums));
        support[epoch] = 0;
    }
}

/* The full search reads only an active cell and its immediate left/right
 * neighbors. All inactive neighbors must be -infinity, even when the same
 * workspace scored them in a previous call. Leave unobservable cells alone. */
static inline void leo_pruning_publish(double *grid, const float *sums,
    const int32_t *support, int n, int bins, size_t stride, const int *epochs, int count)
{
    for (int f = 0; f < bins; ++f) {
        double *row = grid + (size_t)f * (size_t)n;
        for (int i = 0; i < count; ++i) {
            const int epoch = epochs[i];
            if (epoch > 0 && (i == 0 || epochs[i-1] < epoch - 1)) row[epoch-1] = -INFINITY;
            if (epoch + 1 < n && (i + 1 == count || epochs[i+1] > epoch + 1)) row[epoch+1] = -INFINITY;
            row[epoch] = support[epoch] > 0 ?
                (double)sums[stride * (size_t)epoch + (size_t)f] / support[epoch] : -INFINITY;
        }
    }
}
#endif
