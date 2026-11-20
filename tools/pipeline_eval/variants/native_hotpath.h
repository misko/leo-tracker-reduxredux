#ifndef LEO_NATIVE_HOTPATH_H
#define LEO_NATIVE_HOTPATH_H

#include "native_glrt.h"
#include "center_union.h"

#define LEO_NATIVE_HOTPATH_TIMES 200000
#define LEO_NATIVE_HOTPATH_FRAME 13333
#define LEO_NATIVE_HOTPATH_FILTER_FLOATS (2u * 2u * 3u * 32768u)

enum { LEO_HOTPATH_STOCK, LEO_HOTPATH_FIFTH, LEO_HOTPATH_ABSENT };
typedef struct leo_native_hotpath leo_native_hotpath;

typedef struct {
    int32_t hints[2];
    leo_center_union_trace union_trace;
    leo_native_glrt_profile stock_profile;
    double scout_cpu_ms, scout_wall_ms;
    double rank_cpu_ms, rank_wall_ms;
    double detector_cpu_ms, detector_wall_ms;
} leo_native_hotpath_trace_v1;

/* Both templates contain FRAME complex doubles. Optional scout filters contain
 * FILTER_FLOATS interleaved float scalars and 2 * FRAME doubles for energy. Both
 * optional pointers may be null when the context only serves stock/absent mode.
 * All reference data is copied. Serialize context creation and destruction,
 * as with the underlying FFTW planner. A context may serve one caller at a time. */
int leo_native_hotpath_create_v1(leo_native_hotpath **ctx,
    const leo_native_glrt_complex *exact, const leo_native_glrt_complex *control,
    const float *filter, const double *energy);
void leo_native_hotpath_destroy_v1(leo_native_hotpath *ctx);

/* IQ contains exactly TIMES packed, little-endian dual [rx0 I,Q, rx1 I,Q]
 * int16 sample times at 10 MS/s. Caller owns output storage; reuse it per visit.
 * Trace is optional. Treat outputs as invalid when the return code is nonzero. */
int leo_native_hotpath_analyze_v1(leo_native_hotpath *ctx, int mode,
    const int16_t *iq, size_t count, leo_native_glrt_result *out,
    leo_native_hotpath_trace_v1 *trace);

/* Field layout guards are usable without a detector context. */
size_t leo_native_hotpath_trace_size_v1(void);
size_t leo_native_hotpath_result_size_v1(void);
#endif
