#ifndef LEO_ANALYSIS_SINGLE_RX_GLRT_H
#define LEO_ANALYSIS_SINGLE_RX_GLRT_H

#include "native_glrt.h"

#define LEO_SINGLE_RX_GLRT_ABI_VERSION 1u

typedef struct leo_single_rx_glrt leo_single_rx_glrt;

typedef struct {
    uint32_t abi_version;
    uint32_t receiver_count;
    uint32_t input_scalar_stride;
    uint32_t probe_ms;
    uint32_t process_serialized;
    uint32_t maximum_candidates_per_row;
    uint32_t native_per_receiver_semantics;
    uint32_t peer_recovery_available;
    uint32_t fractional_epoch_mode_available;
    uint32_t fractional_epoch_server_parity_qualified;
} leo_single_rx_glrt_capabilities;

/* A single-receiver context consumes interleaved signed-16 [sample][I,Q]. It
 * executes the same proposal and regional eight-candidate search used for one
 * receiver of the ordinary native detector. No peer is synthesized, processed,
 * recovered, or reported. Lifecycle and same-context BUSY rules match the
 * native detector. */
int leo_single_rx_glrt_create(leo_single_rx_glrt **out,uint32_t sample_rate_hz,
    const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template,size_t template_complex_count);
int leo_single_rx_glrt_create_with_mode(leo_single_rx_glrt **out,
    uint32_t sample_rate_hz,const leo_native_glrt_complex *exact_template,
    const leo_native_glrt_complex *control_template,size_t template_complex_count,
    uint32_t mode);
int leo_single_rx_glrt_destroy(leo_single_rx_glrt *context);
int leo_single_rx_glrt_layout(uint32_t sample_rate_hz,uint32_t dwell_ms,
    uint32_t probe_stride_ms,size_t *complex_times,size_t *row_count);
int leo_single_rx_glrt_analyze(leo_single_rx_glrt *context,
    const int16_t *single_rx_iq,size_t complex_times,uint32_t dwell_ms,
    uint32_t probe_stride_ms,leo_native_glrt_result *result);
int leo_single_rx_glrt_analyze_profiled(leo_single_rx_glrt *context,
    const int16_t *single_rx_iq,size_t complex_times,uint32_t dwell_ms,
    uint32_t probe_stride_ms,leo_native_glrt_result *result,
    leo_native_glrt_profile *profile);
int leo_single_rx_glrt_get_capabilities(leo_single_rx_glrt_capabilities *out);

#endif
