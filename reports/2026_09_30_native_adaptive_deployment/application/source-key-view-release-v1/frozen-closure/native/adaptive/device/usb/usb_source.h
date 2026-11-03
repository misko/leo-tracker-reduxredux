#ifndef LEO_ADAPTIVE_USB_SOURCE_H
#define LEO_ADAPTIVE_USB_SOURCE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_USB_SOURCE_ABI_VERSION 1u
#define LEO_USB_SAMPLE_FORMAT_CI16 1u

enum leo_usb_counter_authority {
    LEO_USB_COUNTER_NONE = 0,
    /* Counts delivered sample-times only. It cannot expose samples lost before
     * delivery and is never a hardware counter. */
    LEO_USB_COUNTER_SOFTWARE_DELIVERED = 1,
    LEO_USB_COUNTER_PROVIDER_ESTIMATED = 2,
    LEO_USB_COUNTER_PROVIDER_EXACT = 3
};

enum leo_usb_time_authority {
    LEO_USB_TIME_NONE = 0,
    LEO_USB_TIME_HOST_MONOTONIC = 1,
    LEO_USB_TIME_DEVICE = 2
};

enum leo_usb_capability_flags {
    LEO_USB_CAP_EXCLUSIVE_OPEN = 1u << 0,
    LEO_USB_CAP_CANCEL = 1u << 1,
    LEO_USB_CAP_OVERFLOW_REPORTING = 1u << 2,
    LEO_USB_CAP_RETUNE = 1u << 3,
    LEO_USB_CAP_SIMULTANEOUS_RX = 1u << 4,
    LEO_USB_CAP_COHERENT_RX = 1u << 5,
    /* A successful retune guarantees that no subsequently delivered sample
     * belongs to the preceding tuning. With no provider counter, the USB
     * source may therefore expose its current software-delivery ordinal as the
     * validity boundary. This is an explicit provider guarantee, never an
     * inference from frequency readback. */
    LEO_USB_CAP_RETUNE_VALID_DELIVERY_BOUNDARY = 1u << 6
};

enum leo_usb_block_flags {
    LEO_USB_BLOCK_OVERFLOW_BEFORE = 1u << 0,
    LEO_USB_BLOCK_DISCONTINUITY = 1u << 1,
    LEO_USB_BLOCK_GAP_EXACT = 1u << 2
};

enum leo_usb_retune_flags {
    LEO_USB_RETUNE_VALID_COUNTER = 1u << 0,
    LEO_USB_RETUNE_VALID_TIME = 1u << 1
};

typedef struct leo_usb_capabilities {
    uint32_t abi_version;
    uint32_t sample_format_mask;
    uint32_t flags;
    uint32_t max_receivers;
    uint32_t max_samples_per_block;
    /* Counter authority is fixed for every delivered provider block. A time
     * source may be absent on a block, but any present timestamp has this one
     * authority and epoch for the lifetime of the source. */
    uint32_t counter_authority;
    uint32_t time_authority;
    uint64_t minimum_time_uncertainty_ns;
    uint64_t minimum_sample_rate_hz;
    uint64_t maximum_sample_rate_hz;
    uint64_t minimum_bandwidth_hz;
    uint64_t maximum_bandwidth_hz;
    uint64_t minimum_frequency_hz;
    uint64_t maximum_frequency_hz;
} leo_usb_capabilities;

typedef struct leo_usb_config {
    uint32_t abi_version;
    const char *selector;
    uint32_t sample_rate_hz;
    uint32_t analog_bandwidth_hz;
    uint32_t samples_per_block;
    uint32_t receiver_count;
    uint64_t center_frequency_hz;
    uint64_t maximum_frequency_error_hz;
    uint64_t maximum_time_uncertainty_ns;
    uint32_t require_exact_counter;
    uint32_t require_device_time;
} leo_usb_config;

/* A provider block is valid until capture_release. CI16 is laid out as
 * sample, receiver, I/Q. Authorities and uncertainty describe this block,
 * not an inferred host arrival time. */
typedef struct leo_usb_provider_block {
    const int16_t *ci16;
    size_t iq_bytes;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
    uint32_t flags;
    uint32_t counter_authority;
    uint32_t time_authority;
    uint64_t first_counter;
    uint64_t first_time_ns;
    uint64_t time_uncertainty_ns;
    uintptr_t token;
} leo_usb_provider_block;

typedef struct leo_usb_provider_retune {
    uint64_t actual_frequency_hz;
    uint32_t flags;
    uint32_t counter_authority;
    uint32_t time_authority;
    uint64_t valid_counter;
    uint64_t valid_time_ns;
    uint64_t time_uncertainty_ns;
} leo_usb_provider_retune;

/* open_exclusive must return -EBUSY rather than share an adapter-owned device.
 * capture_cancel must be safe while capture_acquire is blocked. */
typedef struct leo_usb_provider_ops {
    uint32_t abi_version;
    void *context;
    /* probe is read-only: it must not tune, activate a stream, or retain the
     * selected device after returning. */
    int (*probe)(void *context, const char *selector,
        leo_usb_capabilities *capabilities);
    int (*open_exclusive)(void *context, const leo_usb_config *config,
        void **capture);
    int (*capture_acquire)(void *context, void *capture,
        leo_usb_provider_block *block);
    int (*capture_cancel)(void *context, void *capture);
    int (*capture_release)(void *context, void *capture, uintptr_t token);
    int (*retune)(void *context, void *capture, uint64_t frequency_hz,
        leo_usb_provider_retune *receipt);
    int (*capture_close)(void *context, void *capture);
} leo_usb_provider_ops;

typedef struct leo_usb_block {
    const int16_t *ci16;
    size_t iq_bytes;
    uint32_t samples_per_receiver;
    uint32_t receiver_count;
    uint32_t flags;
    uint32_t counter_authority;
    uint32_t time_authority;
    uint64_t stream_ordinal;
    uint64_t first_counter;
    uint64_t first_time_ns;
    uint64_t time_uncertainty_ns;
    uint64_t missing_samples_before;
    uint64_t buffer_sequence;
    uintptr_t lease_token;
} leo_usb_block;

/* Read-only normalized state for narrow adapters. Existing public structures
 * remain unchanged. delivered_watermark is the end of data delivered so far;
 * it is not a coherent-current source position. */
typedef struct leo_usb_stream_info {
    uint32_t abi_version;
    uint32_t sample_format;
    uint32_t capability_flags;
    uint32_t sample_rate_hz;
    uint32_t receiver_count;
    uint32_t maximum_samples_per_block;
    uint32_t counter_authority;
    uint32_t time_authority;
    uint32_t watermark_valid;
    uint64_t minimum_time_uncertainty_ns;
    uint64_t delivered_watermark;
} leo_usb_stream_info;

typedef struct leo_usb_source leo_usb_source;

int leo_usb_source_probe(const char *selector,
    const leo_usb_provider_ops *provider, leo_usb_capabilities *capabilities);
int leo_usb_source_open(const leo_usb_config *config,
    const leo_usb_provider_ops *provider, leo_usb_source **source);
/* Single-owner read. Returns -EBUSY while a block is leased and -EIO after the
 * source has faulted. Provider NONE is normalized to SOFTWARE_DELIVERED. */
int leo_usb_source_get_stream_info(const leo_usb_source *source,
    leo_usb_stream_info *info);
int leo_usb_source_next(leo_usb_source *source, leo_usb_block *block);
/* The first exact-counter block has no preceding adapter boundary, so it does
 * not carry GAP_EXACT. Later exact-counter blocks do, including zero gaps. */
int leo_usb_source_release(leo_usb_source *source, leo_usb_block *block);
int leo_usb_source_retune(leo_usb_source *source, uint64_t frequency_hz,
    leo_usb_provider_retune *receipt);
int leo_usb_source_cancel(leo_usb_source *source);
int leo_usb_source_close(leo_usb_source *source);

#ifdef __cplusplus
}
#endif
#endif
