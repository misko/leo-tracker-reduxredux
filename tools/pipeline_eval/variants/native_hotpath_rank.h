#ifndef LEO_NATIVE_HOTPATH_RANK_H
#define LEO_NATIVE_HOTPATH_RANK_H

#include <math.h>

static int native_hotpath_peak(const double *scores, int n, int i)
{
    double here = scores[i];
    double left = scores[i ? i - 1 : n - 1];
    double right = scores[i + 1 == n ? 0 : i + 1];
    return here > 0.0 && here >= left && here >= right && (here > left || here > right);
}

/* The production consumer uses only the first peak. The separation radius
 * applies to later peaks, so one ascending scan preserves exact tie order. */
static inline int native_hotpath_first(const double *scores, int n, int *epoch)
{
    double best = 0.0;
    *epoch = -1;
    for (int i = 0; i < n; ++i) {
        if (!isfinite(scores[i])) return -1;
        if (scores[i] > best && native_hotpath_peak(scores, n, i)) {
            best = scores[i];
            *epoch = i;
        }
    }
    return 0;
}
#endif
