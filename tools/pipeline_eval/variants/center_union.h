#ifndef LEO_CENTER_UNION_H
#define LEO_CENTER_UNION_H

#include <math.h>
#include "native_glrt.h"

typedef struct {
    int32_t count, ordinary[4], hint, added_epochs, active_epochs;
    int32_t stock_epoch_count, stock_epochs[12];
    uint32_t stock_peak_masks[12];
    int32_t stock_peaks, extra_peaks, retained_stock, retained_extra;
} leo_center_union_lane;

typedef struct { leo_center_union_lane lanes[2]; } leo_center_union_trace;

int leo_native_glrt_analyze_center_union_v1(leo_native_glrt *context,
    const int16_t *ci16,size_t complex_times,const int32_t hints[2],
    leo_native_glrt_result *result,leo_center_union_trace *trace);

static inline int leo_hint_valid(int hint,int period)
{
    return hint >= -1 && hint < period;
}

static inline int leo_union_add(unsigned char *mask,int period,int hint)
{
    if (hint<0) return 0;
    int added=0;
    for (int epoch=hint-1;epoch<=hint+1;++epoch) {
        if (epoch>=0 && epoch<period && !mask[epoch]) {
            mask[epoch]=2;
            ++added;
        }
    }
    return added;
}

/* Stock candidates retain their original one-bin neighbor tests. Only new
 * epochs use all observed neighbors from the union. */
static inline int leo_union_local_peak(const double *row,const unsigned char *mask,
    int period,int epoch)
{
    const unsigned tested=mask[epoch]==1 ? 1u : 3u;
    const double left=epoch>0 && (mask[epoch-1]&tested) ? row[epoch-1] : -INFINITY;
    const double right=epoch+1<period && (mask[epoch+1]&tested) ? row[epoch+1] : -INFINITY;
    const double value=row[epoch];
    return value>=left && value>=right && (value>left || value>right);
}

#endif
