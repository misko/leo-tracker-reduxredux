#ifndef LEO_ADAPTIVE_SCANNER_PROFILE_H
#define LEO_ADAPTIVE_SCANNER_PROFILE_H

#include "scanner_source.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_SCANNER_PROFILE_ABI_VERSION 1u

/* The corrected wideband profile is an additive scanner composition.  It does
 * not extend scanner ABI v2 or the public detector ABI. */
typedef struct leo_scanner_profile_capabilities {
    uint32_t abi_version;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t probe_ms;
    uint32_t probe_stride_ms;
    uint32_t process_serialized;
    uint32_t fractional_epoch_mode_available;
    uint32_t fractional_epoch_server_parity_qualified;
    /* These are distinct properties: frequency-grid storage and the adaptive
     * peer-recovery symbol set happen to contain 22 entries in profile v1. */
    uint32_t coarse_cfo_storage_slots;
    uint32_t peer_fallback_anchor_symbols;
    uint64_t maximum_residual_span_hz;
} leo_scanner_profile_capabilities;

/* Value-owned authority presented after source-transition validation and
 * before capture.  The callback must derive geometry only from this value and
 * immutable state bound by profile_manifest_digest. */
typedef struct leo_scanner_visit_authority {
    uint32_t abi_version;
    uint64_t session;
    uint64_t generation;
    uint64_t visit;
    uint32_t target_index;
    uint32_t target_key;
    uint32_t profile_crc32;
    uint32_t transition_flags;
    uint64_t actual_frequency_hz;
    uint64_t selection_counter;
    uint64_t transition_previous_valid_end;
    uint64_t transition_valid_start;
    uint64_t valid_start;
    uint64_t valid_end;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t dwell_ms;
    uint32_t probe_stride_ms;
} leo_scanner_visit_authority;

/* Copied into the bounded scanner slot before detector submission.  No field
 * borrows callback or source storage. */
typedef struct leo_scanner_detector_geometry {
    uint32_t abi_version;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t probe_ms;
    uint32_t probe_stride_ms;
    double receiver_center_hz[2];
    double residual_cfo_min_hz;
    double residual_cfo_max_hz;
    uint8_t profile_manifest_digest[32];
    uint8_t authority_digest[32];
} leo_scanner_detector_geometry;

typedef struct leo_scanner_geometry_port {
    void *context;
    int (*derive)(void *context, const leo_scanner_visit_authority *visit,
        leo_scanner_detector_geometry *geometry);
    uint8_t profile_manifest_digest[32];
} leo_scanner_geometry_port;

/* The adapter owns a detector context.  It receives the immutable per-visit
 * geometry and converts its private result into the public result explicitly;
 * implementations must not cast or memcpy incompatible private structures. */
typedef struct leo_scanner_profile_detector_ops {
    void *context;
    int (*analyze)(void *context,
        const leo_scanner_detector_geometry *geometry,
        const int16_t *dual_rx_iqiq, size_t complex_times,
        uint32_t dwell_ms, uint32_t probe_stride_ms,
        leo_native_glrt_result *result);
    int (*capabilities)(void *context,
        leo_scanner_profile_capabilities *capabilities);
} leo_scanner_profile_detector_ops;

typedef struct leo_scanner_profile_detector_binding {
    uint32_t abi_version;
    leo_scanner_profile_detector_ops ops;
    uint8_t configuration_digest[32];
} leo_scanner_profile_detector_binding;

typedef struct leo_scanner_profile_execution_options {
    uint32_t abi_version;
    uint32_t detector_worker_count;
    const leo_scanner_profile_detector_binding *detectors;
    leo_scanner_geometry_port geometry;
} leo_scanner_profile_execution_options;

/* Additive corrected-profile composition.  Version 1 is deliberately narrow:
 * dual receiver, 7.5 MS/s, 20 ms probes at 120 ms visit offsets, serialized
 * detector execution, 22 coarse-CFO storage slots, 22 peer fallback symbols,
 * and a residual span no wider than the detector-reported limit (qualified at
 * 1.6 MHz).  Geometry derivation happens before capture and a failure admits no
 * detector job.  Existing scanner entrypoints retain their exact behavior. */
int leo_scanner_run_source_profiled_ex(
    const leo_scanner_config *config, leo_source_port *source,
    const leo_scanner_source_requirements *requirements,
    const leo_scanner_profile_execution_options *execution,
    leo_scanner_source_event_sink sink, void *sink_context,
    leo_scanner_source_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
