#ifndef LEO_ADAPTIVE_SCANNER_SINGLE_SOURCE_H
#define LEO_ADAPTIVE_SCANNER_SINGLE_SOURCE_H

#include "scanner_source.h"

#ifdef __cplusplus
extern "C" {
#endif

#include "../detector/single_rx_glrt.h"

#define LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION 1u

typedef struct leo_scanner_single_detector_ops {
    void *context;
    int (*analyze)(void *context, const int16_t *single_rx_iq,
        size_t complex_times, uint32_t dwell_ms, uint32_t probe_stride_ms,
        leo_native_glrt_result *result);
    int (*capabilities)(void *context,
        leo_single_rx_glrt_capabilities *capabilities);
} leo_scanner_single_detector_ops;

/* configuration_digest is caller attestation over the detector build,
 * algorithm, single-receiver input layout, sample rate, exact/control template
 * hashes, and selected mode. The scanner compares these bytes but cannot
 * inspect the context against them. */
typedef struct leo_scanner_single_detector_binding {
    uint32_t abi_version;
    leo_scanner_single_detector_ops ops;
    uint8_t configuration_digest[32];
} leo_scanner_single_detector_binding;

typedef struct leo_scanner_single_execution_options {
    uint32_t abi_version;
    uint32_t detector_worker_count;
    const leo_scanner_single_detector_binding *detectors;
} leo_scanner_single_execution_options;

/* Additive one-receiver software-watermark profile. config.receiver_count must
 * be one. requirements must declare SOFTWARE_DELIVERED / DELIVERED_WATERMARK,
 * require CANCEL, SELECT, FREQUENCY_ATTESTATION and VALID_SELECTION_BOUNDARY,
 * require FREQUENCY_ATTESTED and VALID_COUNTER_BOUNDARY transitions, and must
 * not require physical-counter qualification. Target profile is a logical
 * policy key; no target, profile CRC, exact-gap, UTC, or physical revisit
 * authority is manufactured. Events and stats use the unchanged common-source
 * envelope and remain caller-bound to this invocation. */
int leo_scanner_run_source_single_ex(const leo_scanner_config *config,
    leo_source_port *source,
    const leo_scanner_source_requirements *requirements,
    const leo_scanner_single_execution_options *execution,
    leo_scanner_source_event_sink sink,
    void *sink_context,
    leo_scanner_source_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
