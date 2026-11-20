#ifndef LEO_HINTED_GLRT_H
#define LEO_HINTED_GLRT_H

#include "native_glrt.h"

typedef struct {
    int32_t count, ordinary[4], selected[4], active_epochs;
} leo_hint_lane;

typedef struct {
    leo_hint_lane lanes[2];
} leo_hinted_glrt_trace;

/* Null is -1 per lane. Keep the original shapes and one-shot result ABI. */
int leo_native_glrt_analyze_hinted_v1(leo_native_glrt *context,
    const int16_t *ci16, size_t complex_times, const int32_t hints[2],
    leo_native_glrt_result *out, leo_hinted_glrt_trace *trace);

static inline int leo_hint_valid(int hint, int period)
{
    return hint >= -1 && hint < period;
}

static inline void leo_hint_centers(int centers[4], int count, int hint,
    int period, leo_hint_lane *trace)
{
    *trace=(leo_hint_lane){.count=count};
    for (int j=0; j<count; ++j) trace->ordinary[j]=centers[j];
    if (count==4 && hint>=0) {
        int novel=1;
        for (int j=0; j<count; ++j) {
            const int d=hint>=centers[j] ? hint-centers[j] : centers[j]-hint;
            if (d<=2 || period-d<=2) novel=0;
        }
        if (novel) centers[3]=hint;
    }
    for (int j=0; j<count; ++j) trace->selected[j]=centers[j];
}

#endif
