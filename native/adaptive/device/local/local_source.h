#ifndef LEO_ADAPTIVE_LOCAL_SOURCE_H
#define LEO_ADAPTIVE_LOCAL_SOURCE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_LOCAL_SOURCE_ABI_VERSION 1u
#define LEO_LOCAL_MAX_PROFILES 8u

typedef struct leo_local_profile {
    uint32_t profile;
    uint64_t frequency_hz;
    uint32_t crc32;
} leo_local_profile;

typedef struct leo_local_config {
    uint32_t sample_rate_hz;
    uint32_t analog_bandwidth_hz;
    uint32_t samples_per_block;
    uint32_t receiver_count;
    uint32_t kernel_buffer_count;
    uint32_t profile_count;
    leo_local_profile profiles[LEO_LOCAL_MAX_PROFILES];
} leo_local_config;

typedef struct leo_local_provider_block {
    const void *raw;
    size_t raw_bytes;
    uintptr_t token;
} leo_local_provider_block;

/* The production provider is local libiio plus the local counter character
 * device. Tests inject the same narrow port; no network/USB transport appears
 * in this contract. ioctl_call deliberately matches the pinned scan-radio ABI. */
typedef struct leo_local_provider_ops {
    void *context;
    int (*capture_open)(void *context, const leo_local_config *config, void **capture);
    int (*capture_acquire)(void *context, void *capture, leo_local_provider_block *block);
    /* Must be safe from a deadline thread while capture_acquire is blocked. */
    int (*capture_cancel)(void *context, void *capture);
    int (*capture_release)(void *context, void *capture, uintptr_t token);
    int (*capture_close)(void *context, void *capture);
    int (*counter_open)(void);
    int (*counter_close)(int fd);
    int (*ioctl_call)(int fd, unsigned long request, void *argument);
} leo_local_provider_ops;

typedef struct leo_local_prime_receipt {
    uint64_t discarded_first_counter;
    uint64_t discarded_end_counter;
    uint64_t coherent_counter;
} leo_local_prime_receipt;

typedef struct leo_local_transition {
    uint32_t profile;
    uint64_t frequency_hz;
    uint32_t profile_crc32;
    uint64_t previous_valid_end;
    uint64_t valid_start;
} leo_local_transition;

typedef struct leo_local_block {
    const void *ci16;
    size_t iq_bytes;
    uint64_t first_counter;
    uint64_t end_counter;
    uint64_t buffer_sequence;
    uint64_t missing_samples_before;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
    uintptr_t lease_token;
} leo_local_block;

typedef struct leo_local_slice {
    const void *ci16;
    size_t iq_bytes;
    uint64_t first_counter;
    uint32_t sample_offset;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
} leo_local_slice;

typedef struct leo_local_restore_receipt {
    uint64_t frequency_hz;
    uint64_t counter_before;
    uint64_t counter_after;
} leo_local_restore_receipt;

typedef struct leo_local_source leo_local_source;
typedef struct leo_local_owner leo_local_owner;

/* Reserve the counter-device fd/flock/kernel session before bufferless radio
 * preparation. Firmware ACQUIRE occurs later in source_open_owned. The same
 * reservation is recovered from source-close and held through restoration. */
int leo_local_owner_acquire(const leo_local_config *config,
    const leo_local_provider_ops *provider, leo_local_owner **owner);
int leo_local_owner_deactivate(leo_local_owner *owner, uint64_t counter_anchor,
    leo_local_restore_receipt *receipt);
int leo_local_owner_release(leo_local_owner *owner, uint64_t counter_anchor,
    leo_local_restore_receipt *receipt);
int leo_local_owner_is_live(const leo_local_owner *owner);
int leo_local_owner_is_active(const leo_local_owner *owner);
int leo_local_source_open_owned(const leo_local_config *config,
    const leo_local_provider_ops *provider, leo_local_owner *owner,
    leo_local_source **source);
int leo_local_source_close_preserve_owner(leo_local_source *source,
    leo_local_owner **owner);

int leo_local_source_open(
    const leo_local_config *config,
    const leo_local_provider_ops *provider,
    leo_local_source **source);
/* Consume and discard one completed DMA block to bind the full-width DMA
 * counter to the firmware's coherent low-word snapshot before any retune. */
int leo_local_source_prime(leo_local_source *source, leo_local_prime_receipt *receipt);
int leo_local_source_recall(
    leo_local_source *source,
    uint32_t profile,
    leo_local_transition *transition);
int leo_local_source_snapshot(leo_local_source *source, uint64_t *counter);
/* Copy the immutable configuration used to open this source. This does not
 * acquire a block or query mutable radio state. */
int leo_local_source_describe(const leo_local_source *source,
    leo_local_config *config);
int leo_local_source_next(leo_local_source *source, leo_local_block *block);
/* Interrupt a blocking next call. This does not close or transfer ownership. */
int leo_local_source_cancel(leo_local_source *source);
int leo_local_source_release(leo_local_source *source, leo_local_block *block);
/* Intersect a leased block with an exact source-counter validity interval.
 * The returned pointer remains valid only while the parent block is leased. */
int leo_local_block_clip(
    const leo_local_block *block,
    uint64_t valid_start,
    uint64_t valid_end,
    leo_local_slice *slice);
/* Close releases an outstanding block, restores the pre-scan frequency via
 * the firmware owner, closes local capture, and destroys the source. */
int leo_local_source_close(
    leo_local_source *source,
    leo_local_restore_receipt *receipt);

/* Local libiio implementation. This symbol never creates a network or USB
 * context. The returned table has static lifetime. */
const leo_local_provider_ops *leo_local_iio_provider(void);

#ifdef __cplusplus
}
#endif
#endif
