#ifndef LEO_INCREMENTAL_RESCUE_H
#define LEO_INCREMENTAL_RESCUE_H

#include "native_glrt.h"

typedef int32_t (*leo_incremental_proposal)(int32_t receiver);

enum {
    LEO_RESCUE_STOCK_POSITIVE, LEO_RESCUE_NO_HINT, LEO_RESCUE_OVERLAP,
    LEO_RESCUE_NEGATIVE, LEO_RESCUE_ACCEPTED
};

typedef struct {
    int32_t count, ordinary[4], hint, requested, evaluated, decision;
    double scout_cpu_ms, scout_wall_ms, rescue_cpu_ms, rescue_wall_ms;
} leo_incremental_lane;

typedef struct { leo_incremental_lane lanes[2]; } leo_incremental_trace;

int leo_native_glrt_analyze_incremental_v1(leo_native_glrt *context,
    const int16_t *ci16,size_t complex_times,leo_incremental_proposal propose,
    leo_native_glrt_result *result,leo_incremental_trace *trace);

#endif
