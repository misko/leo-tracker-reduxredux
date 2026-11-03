#ifndef LEO_ANALYSIS_SHORT_WINDOW_GLRT_H
#define LEO_ANALYSIS_SHORT_WINDOW_GLRT_H

#include "native_glrt.h"
#include "single_rx_glrt.h"

/* Additive, production-native offline entry points. Exactly rate/50 captured
 * complex sample times are required: no padding or implied dwell support.
 * Context templates, search modes, lifecycle and BUSY rules are unchanged.
 * Each receiver has one row with probe_index=0 and probe_start_ms=0; callers
 * project support from the recording's actual sample bounds. Results/profiles
 * are committed only on success. This does not qualify server-reference parity.
 * These symbols are available in release builds, not research builds. */
int leo_native_glrt_short_window_layout(uint32_t sample_rate_hz,
    size_t *complex_times,size_t *row_count);
int leo_native_glrt_analyze_short_window(leo_native_glrt *context,
    const int16_t *dual_rx_iqiq,size_t complex_times,
    leo_native_glrt_result *result);
int leo_native_glrt_analyze_short_window_profiled(leo_native_glrt *context,
    const int16_t *dual_rx_iqiq,size_t complex_times,
    leo_native_glrt_result *result,leo_native_glrt_profile *profile);
int leo_single_rx_glrt_short_window_layout(uint32_t sample_rate_hz,
    size_t *complex_times,size_t *row_count);
int leo_single_rx_glrt_analyze_short_window(leo_single_rx_glrt *context,
    const int16_t *single_rx_iq,size_t complex_times,
    leo_native_glrt_result *result);
int leo_single_rx_glrt_analyze_short_window_profiled(leo_single_rx_glrt *context,
    const int16_t *single_rx_iq,size_t complex_times,
    leo_native_glrt_result *result,leo_native_glrt_profile *profile);

#endif
