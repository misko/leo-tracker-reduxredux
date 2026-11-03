#ifndef LEO_ADAPTIVE_LOCAL_RADIO_PREPARE_H
#define LEO_ADAPTIVE_LOCAL_RADIO_PREPARE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_LOCAL_RADIO_PREPARE_ABI_VERSION 1u
#define LEO_LOCAL_RADIO_MAX_TARGETS 8u
#define LEO_LOCAL_RADIO_PROFILE_BYTES 16u
#define LEO_LOCAL_RADIO_GAIN_MODE_BYTES 24u
#define LEO_LOCAL_RADIO_KERNEL_BUFFERS 16u

typedef struct leo_local_radio_target_request {
    uint32_t profile;
    uint64_t frequency_hz;
} leo_local_radio_target_request;

typedef struct leo_local_radio_prepare_config {
    uint32_t abi_version;
    uint32_t sample_rate_hz;
    uint32_t analog_bandwidth_hz;
    uint32_t receiver_count;
    int32_t manual_gain_millidb;
    uint32_t target_count;
    leo_local_radio_target_request targets[LEO_LOCAL_RADIO_MAX_TARGETS];
} leo_local_radio_prepare_config;

typedef struct leo_local_radio_settings {
    uint64_t center_frequency_hz;
    uint32_t sample_rate_hz;
    uint32_t capture_sample_rate_hz;
    uint32_t analog_bandwidth_hz;
    uint32_t receiver_mask;
    char gain_mode[2][LEO_LOCAL_RADIO_GAIN_MODE_BYTES];
    int32_t gain_millidb[2];
} leo_local_radio_settings;

typedef struct leo_local_radio_prepared_target {
    uint32_t profile;
    uint64_t frequency_hz;
    uint32_t profile_crc32;
    uint8_t profile_bytes[LEO_LOCAL_RADIO_PROFILE_BYTES];
} leo_local_radio_prepared_target;

typedef struct leo_local_radio_prepare_receipt {
    leo_local_radio_settings original;
    leo_local_radio_settings configured;
    uint32_t original_kernel_buffers;
    uint32_t configured_kernel_buffers;
    uint32_t target_count;
    leo_local_radio_prepared_target targets[LEO_LOCAL_RADIO_MAX_TARGETS];
    /* Populated on preparation failure after mutation. */
    uint32_t cleanup_attempted;
    int32_t cleanup_status;
    leo_local_radio_settings cleanup_observed;
    uint32_t cleanup_observed_kernel_buffers;
    uint32_t cleanup_fastlock_inactive;
} leo_local_radio_prepare_receipt;

typedef struct leo_local_radio_restore_receipt {
    leo_local_radio_settings expected;
    leo_local_radio_settings observed;
    uint32_t expected_kernel_buffers;
    uint32_t observed_kernel_buffers;
    uint32_t fastlock_inactive;
} leo_local_radio_restore_receipt;

/* This narrow port is the complete preparation algorithm boundary. Tests use
 * a deterministic fake. The production implementation creates only local:
 * libiio contexts and never creates an IQ buffer. */
typedef struct leo_local_radio_prepare_ops {
    void *context;
    int (*open)(void *context, void **radio);
    int (*close)(void *context, void *radio);
    int (*read_settings)(void *context, void *radio,
        leo_local_radio_settings *settings);
    int (*configure_geometry)(void *context, void *radio,
        const leo_local_radio_prepare_config *config,
        leo_local_radio_settings *observed);
    int (*restore_settings)(void *context, void *radio,
        const leo_local_radio_settings *expected,
        leo_local_radio_settings *observed);
    int (*get_kernel_buffers)(void *context, void *radio, uint32_t *count);
    int (*set_kernel_buffers)(void *context, void *radio,
        uint32_t requested, uint32_t *observed);
    /* active is -1 when ordinary tuning is active, otherwise profile 0..7. */
    int (*read_active_profile)(void *context, void *radio, int32_t *active);
    int (*write_frequency)(void *context, void *radio, uint64_t frequency_hz);
    int (*read_frequency)(void *context, void *radio, uint64_t *frequency_hz);
    int (*store_profile)(void *context, void *radio, uint32_t profile,
        uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES]);
    int (*save_profile)(void *context, void *radio, uint32_t profile,
        uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES]);
    int (*load_profile)(void *context, void *radio, uint32_t profile,
        const uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES]);
    int (*recall_profile)(void *context, void *radio, uint32_t profile);
} leo_local_radio_prepare_ops;

typedef struct leo_local_radio_preparation leo_local_radio_preparation;
typedef struct leo_local_owner leo_local_owner;

/* Read-only check used before firmware-owner acquisition. */
int leo_local_radio_preflight_inactive(
    const leo_local_radio_prepare_ops *ops);

/* Compile, save, reload and attest volatile Fast Lock profiles. On success the
 * handle retains the exact pre-session settings as restoration authority; the
 * underlying IIO context is closed and no RX buffer exists. */
int leo_local_radio_prepare_owned(
    const leo_local_radio_prepare_config *config,
    const leo_local_radio_prepare_ops *ops,
    leo_local_owner *exclusive_owner,
    leo_local_radio_preparation **preparation,
    leo_local_radio_prepare_receipt *receipt);

/* Reopen the same local provider, restore exact RX settings and kernel-buffer
 * count, attest ordinary (non-Fast-Lock) mode, then destroy the handle. A
 * failed restoration retains the handle so the caller can retry. */
int leo_local_radio_restore(
    leo_local_radio_preparation **preparation,
    leo_local_owner *exclusive_owner,
    leo_local_radio_restore_receipt *receipt);

/* Production local-IIO implementation. */
const leo_local_radio_prepare_ops *leo_local_iio_radio_prepare_provider(void);

#ifdef __cplusplus
}
#endif
#endif
