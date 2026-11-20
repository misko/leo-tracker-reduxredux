#ifndef LEO_ADAPTIVE_SOURCE_PORT_H
#define LEO_ADAPTIVE_SOURCE_PORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_SOURCE_PORT_ABI_VERSION 1u
#define LEO_SOURCE_SAMPLE_FORMAT_CI16 1u

enum leo_source_counter_authority {
    LEO_SOURCE_COUNTER_NONE = 0,
    LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED = 1,
    LEO_SOURCE_COUNTER_PROVIDER_ESTIMATED = 2,
    LEO_SOURCE_COUNTER_PROVIDER_EXACT = 3
};

enum leo_source_position_semantics {
    LEO_SOURCE_POSITION_NONE = 0,
    /* A coherent source position sampled when position() is called. */
    LEO_SOURCE_POSITION_COHERENT_CURRENT = 1,
    /* The end of data delivered so far, not the source's current position. */
    LEO_SOURCE_POSITION_DELIVERED_WATERMARK = 2
};

enum leo_source_time_authority {
    LEO_SOURCE_TIME_NONE = 0,
    LEO_SOURCE_TIME_HOST_MONOTONIC = 1,
    /* Provider/device epoch. This is not UTC unless separately qualified. */
    LEO_SOURCE_TIME_DEVICE = 2
};

enum leo_source_capability_flags {
    LEO_SOURCE_CAP_CANCEL = 1u << 0,
    LEO_SOURCE_CAP_SELECT = 1u << 1,
    LEO_SOURCE_CAP_SIMULTANEOUS_RX = 1u << 2,
    LEO_SOURCE_CAP_COHERENT_RX = 1u << 3,
    LEO_SOURCE_CAP_FREQUENCY_ATTESTATION = 1u << 4,
    LEO_SOURCE_CAP_TARGET_ATTESTATION = 1u << 5,
    LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION = 1u << 6,
    LEO_SOURCE_CAP_EXACT_GAP = 1u << 7,
    LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY = 1u << 8
};

enum leo_source_transition_flags {
    LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED = 1u << 0,
    LEO_SOURCE_TRANSITION_TARGET_ATTESTED = 1u << 1,
    LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED = 1u << 2,
    LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY = 1u << 3,
    LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY = 1u << 4
};

enum leo_source_block_flags {
    LEO_SOURCE_BLOCK_OVERFLOW_BEFORE = 1u << 0,
    LEO_SOURCE_BLOCK_DISCONTINUITY = 1u << 1,
    LEO_SOURCE_BLOCK_GAP_EXACT = 1u << 2
};

typedef struct leo_source_capabilities {
    uint32_t abi_version;
    uint32_t sample_format;
    uint32_t flags;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t maximum_samples_per_block;
    uint32_t counter_authority;
    uint32_t position_semantics;
    uint32_t time_authority;
    uint64_t minimum_time_uncertainty_ns;
} leo_source_capabilities;

typedef struct leo_source_position {
    uint64_t coordinate;
    uint32_t counter_authority;
    uint32_t semantics;
} leo_source_position;

typedef struct leo_source_selection {
    uint32_t target_key;
    uint64_t requested_frequency_hz;
    uint64_t maximum_frequency_error_hz;
} leo_source_selection;

typedef struct leo_source_transition {
    uint32_t flags;
    uint32_t selected_target_key;
    uint32_t profile_crc32;
    uint32_t counter_authority;
    uint32_t position_semantics;
    uint32_t time_authority;
    uint64_t actual_frequency_hz;
    uint64_t previous_valid_end;
    uint64_t valid_start;
    uint64_t previous_valid_time_ns;
    uint64_t valid_start_time_ns;
    uint64_t time_uncertainty_ns;
} leo_source_transition;

/* ci16 is borrowed until release. Layout is sample, receiver, I/Q. */
typedef struct leo_source_block {
    const int16_t *ci16;
    size_t iq_bytes;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
    uint32_t flags;
    uint32_t counter_authority;
    uint32_t time_authority;
    uint64_t first_coordinate;
    uint64_t end_coordinate;
    uint64_t stream_ordinal;
    uint64_t first_time_ns;
    uint64_t time_uncertainty_ns;
    uint64_t missing_samples_before;
    uint64_t buffer_sequence;
    uintptr_t lease_token;
} leo_source_block;

typedef struct leo_source_slice {
    const int16_t *ci16;
    size_t iq_bytes;
    uint64_t first_coordinate;
    uint32_t sample_offset;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
} leo_source_slice;

typedef struct leo_source_ops {
    int (*capabilities)(void *context, leo_source_capabilities *capabilities);
    int (*position)(void *context, leo_source_position *position);
    int (*select)(void *context, const leo_source_selection *selection,
        leo_source_transition *transition);
    int (*next)(void *context, leo_source_block *block);
    int (*release)(void *context, leo_source_block *block);
    /* The sole operation allowed concurrently with next(). It must not mutate
     * the port wrapper's lease bookkeeping. */
    int (*cancel)(void *context);
} leo_source_ops;

/* The port and its context remain caller-owned. Initialize before publishing it
 * to a deadline thread. All calls except cancel are single-owner calls. */
typedef struct leo_source_port {
    uint32_t abi_version;
    void *context;
    const leo_source_ops *ops;
    leo_source_capabilities capabilities;
    uintptr_t outstanding_lease;
    leo_source_block retained_block;
    int32_t fault_status;
} leo_source_port;

int leo_source_port_init(leo_source_port *port, void *context,
    const leo_source_ops *ops);
int leo_source_port_capabilities(const leo_source_port *port,
    leo_source_capabilities *capabilities);
int leo_source_port_position(leo_source_port *port,
    leo_source_position *position);
int leo_source_port_select(leo_source_port *port,
    const leo_source_selection *selection, leo_source_transition *transition);
int leo_source_port_next(leo_source_port *port, leo_source_block *block);
int leo_source_port_release(leo_source_port *port, leo_source_block *block);
/* Retry release of a lease retained after provider release failure. A failed
 * retry leaves the port faulted and the lease retained. */
int leo_source_port_cleanup(leo_source_port *port);
int leo_source_port_cancel(leo_source_port *port);
int leo_source_block_clip(const leo_source_block *block, uint64_t valid_start,
    uint64_t valid_end, leo_source_slice *slice);

#ifdef __cplusplus
}
#endif
#endif
