#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "local_radio_prepare.h"

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct iio_context;
struct iio_device;
struct iio_channel;

extern struct iio_context *iio_create_local_context(void);
extern void iio_context_destroy(struct iio_context *context);
extern int iio_context_set_timeout(struct iio_context *context,
    unsigned int timeout_ms);
extern struct iio_device *iio_context_find_device(const struct iio_context *context,
    const char *name);
extern struct iio_channel *iio_device_find_channel(const struct iio_device *device,
    const char *name, bool output);
extern size_t iio_device_get_channels_count(const struct iio_device *device);
extern struct iio_channel *iio_device_get_channel(const struct iio_device *device,
    size_t index);
extern bool iio_channel_is_output(const struct iio_channel *channel);
extern bool iio_channel_is_enabled(const struct iio_channel *channel);
extern void iio_channel_enable(struct iio_channel *channel);
extern void iio_channel_disable(struct iio_channel *channel);
extern const char *iio_channel_find_attr(const struct iio_channel *channel,
    const char *name);
extern ssize_t iio_channel_attr_read(const struct iio_channel *channel,
    const char *attribute, char *destination, size_t length);
extern ssize_t iio_channel_attr_write(const struct iio_channel *channel,
    const char *attribute, const char *source);
extern int iio_channel_attr_read_longlong(const struct iio_channel *channel,
    const char *attribute, long long *value);
extern int iio_channel_attr_write_longlong(const struct iio_channel *channel,
    const char *attribute, long long value);
extern int iio_channel_attr_read_double(const struct iio_channel *channel,
    const char *attribute, double *value);
extern int iio_channel_attr_write_double(const struct iio_channel *channel,
    const char *attribute, double value);
extern int iio_device_set_kernel_buffers_count(const struct iio_device *device,
    unsigned int count);
extern unsigned int iio_device_get_kernel_buffers_count(const struct iio_device *device);
/* v0.59 target exports this; older host libiio used for fake-only builds may not. */
#pragma weak iio_device_get_kernel_buffers_count
extern int iio_device_reg_read(struct iio_device *device, uint32_t address,
    uint32_t *value);

#define ADC_GP_CONTROL_REG UINT32_C(0x800000bc)

struct local_prepare_iio {
    struct iio_context *context;
    struct iio_device *phy;
    struct iio_device *capture;
    struct iio_channel *lo;
};

static int read_string(const struct iio_channel *channel, const char *attribute,
    char *destination, size_t capacity)
{
    ssize_t count;
    if (!channel || !attribute || !destination || capacity < 2U)
        return -EINVAL;
    count = iio_channel_attr_read(channel, attribute, destination, capacity);
    if (count < 0)
        return (int)count;
    if ((size_t)count >= capacity)
        return -EOVERFLOW;
    destination[count] = '\0';
    while (count > 0 && (destination[count - 1] == '\n' ||
            destination[count - 1] == '\r' || destination[count - 1] == '\0'))
        destination[--count] = '\0';
    return 0;
}

static int write_string(const struct iio_channel *channel, const char *attribute,
    const char *value)
{
    ssize_t ret = iio_channel_attr_write(channel, attribute, value);
    return ret < 0 ? (int)ret : 0;
}

static int rx_scan_mask(struct local_prepare_iio *radio, uint32_t *mask)
{
    static const char *const names[4] = {
        "voltage0", "voltage1", "voltage2", "voltage3"
    };
    uint32_t enabled = 0U;
    unsigned i;
    *mask = 0U;
    for (i = 0U; i < 4U; ++i) {
        struct iio_channel *channel = iio_device_find_channel(radio->capture,
            names[i], false);
        if (!channel)
            return -ENODEV;
        if (iio_channel_is_enabled(channel))
            enabled |= 1U << i;
    }
    if ((enabled & 3U) == 3U) *mask |= 1U;
    if ((enabled & 12U) == 12U) *mask |= 2U;
    if (enabled != (*mask == 3U ? 15U : *mask == 1U ? 3U : *mask == 0U ? 0U : 16U))
        return -EPROTO;
    return 0;
}

static int set_rx_scan_mask(struct local_prepare_iio *radio, uint32_t mask)
{
    static const char *const names[4] = {
        "voltage0", "voltage1", "voltage2", "voltage3"
    };
    unsigned i;
    if (mask != 0U && mask != 1U && mask != 3U)
        return -EINVAL;
    for (i = 0U; i < 4U; ++i) {
        struct iio_channel *channel = iio_device_find_channel(radio->capture,
            names[i], false);
        if (!channel)
            return -ENODEV;
        if (i < (mask == 0U ? 0U : mask == 1U ? 2U : 4U))
            iio_channel_enable(channel);
        else
            iio_channel_disable(channel);
    }
    return 0;
}

static int mute_transmit(struct local_prepare_iio *radio)
{
    struct iio_device *dds = iio_context_find_device(radio->context,
        "cf-ad9361-dds-core-lpc");
    unsigned i;
    for (i = 0U; i < 2U; ++i) {
        char name[16];
        struct iio_channel *tx;
        double gain = 0.0;
        snprintf(name, sizeof(name), "voltage%u", i);
        tx = iio_device_find_channel(radio->phy, name, true);
        if (tx && iio_channel_find_attr(tx, "hardwaregain")) {
            int ret = iio_channel_attr_write_double(tx, "hardwaregain", -80.0);
            if (!ret) ret = iio_channel_attr_read_double(tx, "hardwaregain", &gain);
            if (ret) return ret;
            if (gain > -80.0) return -EPROTO;
        }
    }
    if (dds) {
        size_t count = iio_device_get_channels_count(dds);
        for (i = 0U; i < count; ++i) {
            struct iio_channel *channel = iio_device_get_channel(dds, i);
            double scale = 0.0;
            if (!channel || !iio_channel_is_output(channel)) continue;
            if (iio_channel_find_attr(channel, "scale")) {
                int ret = iio_channel_attr_write_double(channel, "scale", 0.0);
                if (!ret) ret = iio_channel_attr_read_double(channel, "scale", &scale);
                if (ret) return ret;
                if (scale != 0.0) return -EPROTO;
            }
            if (iio_channel_find_attr(channel, "raw")) {
                long long raw = 0;
                int ret = iio_channel_attr_write_longlong(channel, "raw", 0);
                if (!ret) ret = iio_channel_attr_read_longlong(channel, "raw", &raw);
                if (ret) return ret;
                if (raw != 0) return -EPROTO;
            }
            iio_channel_disable(channel);
        }
    }
    return 0;
}

static int iio_open(void *unused, void **out)
{
    struct local_prepare_iio *radio;
    int ret;
    (void)unused;
    if (!out) return -EINVAL;
    *out = NULL;
    radio = calloc(1, sizeof(*radio));
    if (!radio) return -ENOMEM;
    radio->context = iio_create_local_context();
    if (!radio->context) {
        ret = errno ? -errno : -ENODEV;
        goto fail;
    }
    ret = iio_context_set_timeout(radio->context, 1000U);
    if (ret) goto fail_context;
    radio->phy = iio_context_find_device(radio->context, "ad9361-phy");
    radio->capture = iio_context_find_device(radio->context, "cf-ad9361-lpc");
    radio->lo = radio->phy ? iio_device_find_channel(radio->phy,
        "altvoltage0", true) : NULL;
    if (!radio->phy || !radio->capture || !radio->lo) {
        ret = -ENODEV;
        goto fail_context;
    }
    *out = radio;
    return 0;
fail_context:
    iio_context_destroy(radio->context);
fail:
    free(radio);
    return ret;
}

static int iio_close(void *unused, void *opaque)
{
    struct local_prepare_iio *radio = opaque;
    (void)unused;
    if (!radio) return -EINVAL;
    iio_context_destroy(radio->context);
    free(radio);
    return 0;
}

static int read_settings(void *unused, void *opaque,
    leo_local_radio_settings *settings)
{
    struct local_prepare_iio *radio = opaque;
    struct iio_channel *rx0;
    struct iio_channel *capture0;
    long long value;
    unsigned i;
    int ret;
    (void)unused;
    if (!radio || !settings) return -EINVAL;
    memset(settings, 0, sizeof(*settings));
    rx0 = iio_device_find_channel(radio->phy, "voltage0", false);
    capture0 = iio_device_find_channel(radio->capture, "voltage0", false);
    if (!rx0 || !capture0) return -ENODEV;
    ret = iio_channel_attr_read_longlong(radio->lo, "frequency", &value);
    if (!ret && value <= 0) ret = -EPROTO;
    if (ret) return ret;
    settings->center_frequency_hz = (uint64_t)value;
    ret = iio_channel_attr_read_longlong(rx0, "sampling_frequency", &value);
    if (!ret && (value <= 0 || value > UINT32_MAX)) ret = -EPROTO;
    if (ret) return ret;
    settings->sample_rate_hz = (uint32_t)value;
    ret = iio_channel_attr_read_longlong(capture0, "sampling_frequency", &value);
    if (!ret && (value <= 0 || value > UINT32_MAX)) ret = -EPROTO;
    if (ret) return ret;
    settings->capture_sample_rate_hz = (uint32_t)value;
    ret = iio_channel_attr_read_longlong(rx0, "rf_bandwidth", &value);
    if (!ret && (value <= 0 || value > UINT32_MAX)) ret = -EPROTO;
    if (ret) return ret;
    settings->analog_bandwidth_hz = (uint32_t)value;
    ret = rx_scan_mask(radio, &settings->receiver_mask);
    if (ret) return ret;
    for (i = 0U; i < 2U; ++i) {
        char name[16];
        struct iio_channel *rx;
        double gain;
        snprintf(name, sizeof(name), "voltage%u", i);
        rx = iio_device_find_channel(radio->phy, name, false);
        if (!rx) return -ENODEV;
        ret = read_string(rx, "gain_control_mode", settings->gain_mode[i],
            sizeof(settings->gain_mode[i]));
        if (ret) return ret;
        ret = iio_channel_attr_read_double(rx, "hardwaregain", &gain);
        if (ret) return ret;
        settings->gain_millidb[i] = (int32_t)(gain * 1000.0 +
            (gain >= 0.0 ? 0.5 : -0.5));
    }
    return 0;
}

static int attest_rate(struct local_prepare_iio *radio, uint32_t requested)
{
    struct iio_channel *phy_rate = iio_device_find_channel(radio->phy,
        "voltage0", false);
    struct iio_channel *capture_rate = iio_device_find_channel(radio->capture,
        "voltage0", false);
    char available[128], *cursor, *end;
    long long phy_observed, capture_observed, rates[2];
    uint32_t gp_control;
    unsigned found = 0U;
    int ret;
    if (!phy_rate || !capture_rate) return -ENODEV;
    ret = iio_channel_attr_write_longlong(phy_rate, "sampling_frequency", requested);
    if (!ret) ret = iio_channel_attr_read_longlong(phy_rate,
        "sampling_frequency", &phy_observed);
    if (!ret) ret = iio_channel_attr_write_longlong(capture_rate,
        "sampling_frequency", requested);
    if (!ret) ret = iio_channel_attr_read_longlong(capture_rate,
        "sampling_frequency", &capture_observed);
    if (ret) return ret;
    if (phy_observed != requested || capture_observed != requested)
        return -EPROTO;
    ret = read_string(capture_rate, "sampling_frequency_available", available,
        sizeof(available));
    if (ret) return ret;
    cursor = available;
    while (*cursor && found < 2U) {
        while (*cursor == ' ' || *cursor == '[' || *cursor == ']') ++cursor;
        if (!*cursor) break;
        errno = 0;
        rates[found] = strtoll(cursor, &end, 10);
        if (errno || end == cursor) return -EPROTO;
        ++found;
        cursor = end;
    }
    while (*cursor == ' ' || *cursor == ']') ++cursor;
    if (found != 2U || *cursor || rates[0] != requested ||
        rates[1] != requested / 8U)
        return -EPROTO;
    ret = iio_device_reg_read(radio->capture, ADC_GP_CONTROL_REG, &gp_control);
    if (ret) return ret;
    return (gp_control & 1U) ? -EPROTO : 0;
}

static int configure_geometry(void *unused, void *opaque,
    const leo_local_radio_prepare_config *config,
    leo_local_radio_settings *observed)
{
    static const char *const rx_names[2] = { "voltage0", "voltage1" };
    struct local_prepare_iio *radio = opaque;
    struct iio_channel *rx0;
    unsigned i;
    int ret;
    (void)unused;
    ret = attest_rate(radio, config->sample_rate_hz);
    if (ret) return ret;
    rx0 = iio_device_find_channel(radio->phy, "voltage0", false);
    ret = iio_channel_attr_write_longlong(rx0, "rf_bandwidth",
        config->analog_bandwidth_hz);
    if (!ret) ret = set_rx_scan_mask(radio,
        (1U << config->receiver_count) - 1U);
    for (i = 0U; !ret && i < config->receiver_count; ++i) {
        struct iio_channel *rx;
        rx = iio_device_find_channel(radio->phy, rx_names[i], false);
        if (!rx) return -ENODEV;
        ret = write_string(rx, "gain_control_mode", "manual");
        if (!ret) ret = iio_channel_attr_write_double(rx, "hardwaregain",
            (double)config->manual_gain_millidb / 1000.0);
    }
    if (!ret) ret = mute_transmit(radio);
    if (!ret) ret = read_settings(NULL, radio, observed);
    for (i = 0U; !ret && i < config->receiver_count; ++i) {
        if (strcmp(observed->gain_mode[i], "manual") ||
            observed->gain_millidb[i] != config->manual_gain_millidb)
            ret = -EPROTO;
    }
    return ret;
}

static int restore_settings(void *unused, void *opaque,
    const leo_local_radio_settings *expected, leo_local_radio_settings *observed)
{
    static const char *const rx_names[2] = { "voltage0", "voltage1" };
    struct local_prepare_iio *radio = opaque;
    struct iio_channel *rx0;
    struct iio_channel *capture0;
    unsigned i;
    int ret = 0, step;
    (void)unused;
    rx0 = iio_device_find_channel(radio->phy, "voltage0", false);
    capture0 = iio_device_find_channel(radio->capture, "voltage0", false);
    if (!rx0 || !capture0) return -ENODEV;
    step = iio_channel_attr_write_longlong(rx0, "sampling_frequency",
        expected->sample_rate_hz);
    if (!ret && step) ret = step;
    step = iio_channel_attr_write_longlong(capture0,
        "sampling_frequency", expected->capture_sample_rate_hz);
    if (!ret && step) ret = step;
    step = iio_channel_attr_write_longlong(rx0, "rf_bandwidth",
        expected->analog_bandwidth_hz);
    if (!ret && step) ret = step;
    step = set_rx_scan_mask(radio, expected->receiver_mask);
    if (!ret && step) ret = step;
    for (i = 0U; i < 2U; ++i) {
        struct iio_channel *rx;
        rx = iio_device_find_channel(radio->phy, rx_names[i], false);
        if (!rx) { if (!ret) ret = -ENODEV; continue; }
        step = write_string(rx, "gain_control_mode", expected->gain_mode[i]);
        if (!ret && step) ret = step;
        if (!strcmp(expected->gain_mode[i], "manual")) {
            step = iio_channel_attr_write_double(rx, "hardwaregain",
                (double)expected->gain_millidb[i] / 1000.0);
            if (!ret && step) ret = step;
        }
    }
    step = mute_transmit(radio);
    if (!ret && step) ret = step;
    /* Force the clock framework through a distinct cached rate, then finish
     * at the exact snapshot frequency so a live Fast Lock state cannot make
     * the final ordinary write a no-op. */
    step = iio_channel_attr_write_longlong(radio->lo, "frequency",
        (long long)(expected->center_frequency_hz <= UINT64_C(5999999998) ?
            expected->center_frequency_hz + 2U : expected->center_frequency_hz - 2U));
    if (!ret && step) ret = step;
    if (!step) {
        long long transition = 0;
        const uint64_t expected_transition =
            expected->center_frequency_hz <= UINT64_C(5999999998) ?
            expected->center_frequency_hz + 2U : expected->center_frequency_hz - 2U;
        step = iio_channel_attr_read_longlong(radio->lo, "frequency", &transition);
        if (!step && (uint64_t)transition != expected_transition) step = -EPROTO;
        if (!ret && step) ret = step;
    }
    step = iio_channel_attr_write_longlong(radio->lo, "frequency",
        (long long)expected->center_frequency_hz);
    if (!ret && step) ret = step;
    step = read_settings(NULL, radio, observed);
    if (!ret && step) ret = step;
    return ret;
}

static int get_buffers(void *unused, void *opaque, uint32_t *count)
{
    struct local_prepare_iio *radio = opaque;
    (void)unused;
    if (!radio || !count) return -EINVAL;
    if (!iio_device_get_kernel_buffers_count) return -ENOTSUP;
    *count = iio_device_get_kernel_buffers_count(radio->capture);
    return *count ? 0 : -EPROTO;
}

static int set_buffers(void *unused, void *opaque, uint32_t requested,
    uint32_t *observed)
{
    struct local_prepare_iio *radio = opaque;
    int ret;
    (void)unused;
    if (!iio_device_get_kernel_buffers_count) return -ENOTSUP;
    ret = iio_device_set_kernel_buffers_count(radio->capture, requested);
    if (!ret) *observed = iio_device_get_kernel_buffers_count(radio->capture);
    return ret;
}

static int active_profile(void *unused, void *opaque, int32_t *active)
{
    struct local_prepare_iio *radio = opaque;
    long long value;
    int ret;
    (void)unused;
    ret = iio_channel_attr_read_longlong(radio->lo, "fastlock_recall", &value);
    if (ret == -EINVAL) {
        *active = -1;
        return 0;
    }
    if (ret) return ret;
    if (value < 0 || value > 7) return -EPROTO;
    *active = (int32_t)value;
    return 0;
}

static int write_frequency(void *unused, void *opaque, uint64_t frequency)
{
    struct local_prepare_iio *radio = opaque;
    (void)unused;
    if (frequency > INT64_MAX) return -ERANGE;
    return iio_channel_attr_write_longlong(radio->lo, "frequency",
        (long long)frequency);
}

static int read_frequency(void *unused, void *opaque, uint64_t *frequency)
{
    struct local_prepare_iio *radio = opaque;
    long long value;
    int ret;
    (void)unused;
    ret = iio_channel_attr_read_longlong(radio->lo, "frequency", &value);
    if (!ret && value <= 0) ret = -EPROTO;
    if (!ret) *frequency = (uint64_t)value;
    return ret;
}

static int parse_profile(const char *text, uint32_t expected,
    uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    char *end;
    unsigned long profile;
    unsigned i;
    errno = 0;
    profile = strtoul(text, &end, 10);
    if (errno || end == text || profile != expected || *end != ' ')
        return -EPROTO;
    text = end + 1;
    for (i = 0U; i < LEO_LOCAL_RADIO_PROFILE_BYTES; ++i) {
        unsigned long value;
        errno = 0;
        value = strtoul(text, &end, 10);
        if (errno || end == text || value > 255U ||
            (i + 1U < LEO_LOCAL_RADIO_PROFILE_BYTES ? *end != ',' : *end != '\0'))
            return -EPROTO;
        bytes[i] = (uint8_t)value;
        text = end + (i + 1U < LEO_LOCAL_RADIO_PROFILE_BYTES ? 1 : 0);
    }
    return 0;
}

static int save_profile(void *unused, void *opaque, uint32_t profile,
    uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct local_prepare_iio *radio = opaque;
    char command[4], response[128];
    int ret;
    (void)unused;
    snprintf(command, sizeof(command), "%u", profile);
    ret = write_string(radio->lo, "fastlock_save", command);
    if (!ret) ret = read_string(radio->lo, "fastlock_save", response,
        sizeof(response));
    if (!ret) ret = parse_profile(response, profile, bytes);
    return ret;
}

static int store_profile(void *unused, void *opaque, uint32_t profile,
    uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct local_prepare_iio *radio = opaque;
    char command[4];
    int ret;
    (void)unused;
    snprintf(command, sizeof(command), "%u", profile);
    ret = write_string(radio->lo, "fastlock_store", command);
    if (!ret) ret = save_profile(NULL, radio, profile, bytes);
    return ret;
}

static int load_profile(void *unused, void *opaque, uint32_t profile,
    const uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct local_prepare_iio *radio = opaque;
    char command[128];
    size_t used;
    unsigned i;
    int count;
    (void)unused;
    count = snprintf(command, sizeof(command), "%u %u", profile, bytes[0]);
    if (count < 0 || (size_t)count >= sizeof(command)) return -EOVERFLOW;
    used = (size_t)count;
    for (i = 1U; i < LEO_LOCAL_RADIO_PROFILE_BYTES; ++i) {
        count = snprintf(command + used, sizeof(command) - used, ",%u", bytes[i]);
        if (count < 0 || (size_t)count >= sizeof(command) - used)
            return -EOVERFLOW;
        used += (size_t)count;
    }
    return write_string(radio->lo, "fastlock_load", command);
}

static int recall_profile(void *unused, void *opaque, uint32_t profile)
{
    struct local_prepare_iio *radio = opaque;
    char command[4];
    (void)unused;
    snprintf(command, sizeof(command), "%u", profile);
    return write_string(radio->lo, "fastlock_recall", command);
}

const leo_local_radio_prepare_ops *leo_local_iio_radio_prepare_provider(void)
{
    static const leo_local_radio_prepare_ops ops = {
        NULL, iio_open, iio_close, read_settings, configure_geometry,
        restore_settings, get_buffers, set_buffers, active_profile,
        write_frequency, read_frequency, store_profile, save_profile,
        load_profile, recall_profile
    };
    return &ops;
}
