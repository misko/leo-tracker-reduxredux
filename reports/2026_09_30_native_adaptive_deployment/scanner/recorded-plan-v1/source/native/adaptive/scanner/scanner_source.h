#ifndef LEO_ADAPTIVE_SCANNER_SOURCE_H
#define LEO_ADAPTIVE_SCANNER_SOURCE_H

#include "scanner.h"
#include "../device/source/source_port.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_SCANNER_SOURCE_ABI_VERSION 1u

typedef struct leo_scanner_source_requirements {
    uint32_t abi_version;
    uint32_t counter_authority;
    uint32_t position_semantics;
    uint32_t required_capability_flags;
    uint32_t required_transition_flags;
    uint64_t maximum_frequency_error_hz;
    /* Requires exact coherent-current counters, exact gaps, simultaneous
     * coherent receivers and valid counter selection boundaries. This is
     * source-counter qualification only; it does not claim UTC authority or
     * end-to-end physical revisit qualification. */
    uint32_t require_physical_counter_qualified;
} leo_scanner_source_requirements;

typedef struct leo_scanner_source_event {
    uint32_t abi_version;
    leo_scanner_event event;
    uint32_t counter_authority;
    uint32_t position_semantics;
    uint32_t time_authority;
    uint32_t transition_flags;
    uint32_t block_flags;
    uint32_t physical_counter_qualified;
} leo_scanner_source_event;

typedef void (*leo_scanner_source_event_sink)(void *context,
    const leo_scanner_source_event *event);

typedef struct leo_scanner_source_stats {
    uint32_t abi_version;
    leo_scanner_stats scanner;
    uint64_t overflow_blocks;
    uint64_t discontinuity_blocks;
    uint64_t unknown_discontinuities;
    uint64_t exact_missing_samples;
    uint32_t counter_authority;
    uint32_t position_semantics;
    uint32_t time_authority;
    uint32_t physical_counter_qualified;
} leo_scanner_source_stats;

/* The source is already open and primed and remains caller-owned. The generic
 * event envelope is mandatory: consumers must explicitly interpret its
 * authority and must not pass an unqualified coordinate to the live Timebase. */
int leo_scanner_run_source(const leo_scanner_config *config,
    leo_source_port *source,
    const leo_scanner_source_requirements *requirements,
    const leo_scanner_detector_ops *detector,
    leo_scanner_source_event_sink sink,
    void *sink_context,
    leo_scanner_source_stats *stats);

/* Multi-context equivalent. Execution/configuration validation is performed
 * before the source capabilities callback or any other source operation. */
int leo_scanner_run_source_ex(const leo_scanner_config *config,
    leo_source_port *source,
    const leo_scanner_source_requirements *requirements,
    const leo_scanner_execution_options *execution,
    leo_scanner_source_event_sink sink,
    void *sink_context,
    leo_scanner_source_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
