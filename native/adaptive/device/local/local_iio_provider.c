#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "local_source.h"

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Minimal public libiio 0.25 ABI declarations. Keeping the integration surface
 * here avoids a build-time dependency on a reference checkout; the ARM link
 * resolves against the source-qualified target libiio. */
struct iio_context;
struct iio_device;
struct iio_channel;
struct iio_buffer;

extern struct iio_context *iio_create_local_context(void);
extern void iio_context_destroy(struct iio_context *context);
extern int iio_context_set_timeout(struct iio_context *context,
    unsigned int timeout_ms);
extern struct iio_device *iio_context_find_device(const struct iio_context *context,
    const char *name);
extern struct iio_channel *iio_device_find_channel(const struct iio_device *device,
    const char *name, bool output);
extern void iio_channel_enable(struct iio_channel *channel);
extern void iio_channel_disable(struct iio_channel *channel);
extern int iio_channel_attr_read_longlong(const struct iio_channel *channel,
    const char *attribute, long long *value);
extern int iio_device_set_kernel_buffers_count(const struct iio_device *device,
    unsigned int count);
extern unsigned int iio_device_get_kernel_buffers_count(const struct iio_device *device)
    __attribute__((weak));
extern ssize_t iio_device_get_sample_size(const struct iio_device *device);
extern struct iio_buffer *iio_device_create_buffer(const struct iio_device *device,
    size_t samples_count, bool cyclic);
extern void iio_buffer_destroy(struct iio_buffer *buffer);
extern ssize_t iio_buffer_refill(struct iio_buffer *buffer);
extern void iio_buffer_cancel(struct iio_buffer *buffer);
extern void *iio_buffer_start(const struct iio_buffer *buffer);

struct local_iio_capture {
    struct iio_context *context;
    struct iio_buffer *buffer;
    size_t raw_bytes;
    uintptr_t token_generation;
    bool outstanding;
};

static int local_capture_open(void *unused, const struct leo_local_config *config,
    void **capture_out)
{
    static const char *const channels[4] = {
        "voltage0", "voltage1", "voltage2", "voltage3"
    };
    struct local_iio_capture *capture;
    struct iio_device *rx, *phy;
    struct iio_channel *channel, *rx0;
    unsigned configured, channel_count, i;
    size_t extra_samples, total_samples;
    long long rate, bandwidth;
    ssize_t sample_size;
    int ret;

    (void)unused;
    if (!config || !capture_out)
        return -EINVAL;
    *capture_out = NULL;
    capture = calloc(1, sizeof(*capture));
    if (!capture)
        return -ENOMEM;
    capture->context = iio_create_local_context();
    if (!capture->context) {
        ret = errno ? -errno : -ENODEV;
        goto fail;
    }
    /* Make the v0.57 local-provider default explicit. Cooperative cancellation
     * remains the application hard-deadline mechanism. */
    ret = iio_context_set_timeout(capture->context, 1000U);
    if (ret)
        goto fail_context;
    rx = iio_context_find_device(capture->context, "cf-ad9361-lpc");
    phy = iio_context_find_device(capture->context, "ad9361-phy");
    rx0 = phy ? iio_device_find_channel(phy, "voltage0", false) : NULL;
    if (!rx || !rx0) {
        ret = -ENODEV;
        goto fail_context;
    }
    if (iio_channel_attr_read_longlong(rx0, "sampling_frequency", &rate) ||
        iio_channel_attr_read_longlong(rx0, "rf_bandwidth", &bandwidth) ||
        rate != config->sample_rate_hz || bandwidth != config->analog_bandwidth_hz) {
        ret = -ERANGE;
        goto fail_context;
    }
    channel_count = config->receiver_count * 2U;
    for (i = 0; i < 4U; ++i) {
        channel = iio_device_find_channel(rx, channels[i], false);
        if (channel)
            iio_channel_disable(channel);
    }
    for (i = 0; i < channel_count; ++i) {
        channel = iio_device_find_channel(rx, channels[i], false);
        if (!channel) {
            ret = -ENODEV;
            goto fail_context;
        }
        iio_channel_enable(channel);
    }
    sample_size = iio_device_get_sample_size(rx);
    if (sample_size != (ssize_t)(config->receiver_count * 4U)) {
        ret = sample_size < 0 ? (int)sample_size : -EPROTO;
        goto fail_context;
    }
    ret = iio_device_set_kernel_buffers_count(rx, config->kernel_buffer_count);
    if (ret)
        goto fail_context;
    configured = iio_device_get_kernel_buffers_count ?
        iio_device_get_kernel_buffers_count(rx) : config->kernel_buffer_count;
    if (configured < 4U) {
        ret = -ENOSPC;
        goto fail_context;
    }
    extra_samples = 8U / (size_t)sample_size;
    if (config->samples_per_block > SIZE_MAX - extra_samples) {
        ret = -EOVERFLOW;
        goto fail_context;
    }
    total_samples = config->samples_per_block + extra_samples;
    capture->buffer = iio_device_create_buffer(rx, total_samples, false);
    if (!capture->buffer) {
        ret = errno ? -errno : -EIO;
        goto fail_context;
    }
    capture->raw_bytes = total_samples * (size_t)sample_size;
    *capture_out = capture;
    return 0;

fail_context:
    iio_context_destroy(capture->context);
fail:
    free(capture);
    return ret;
}

static int local_capture_acquire(void *unused, void *opaque,
    struct leo_local_provider_block *block)
{
    struct local_iio_capture *capture = opaque;
    ssize_t bytes;

    (void)unused;
    if (!capture || !block)
        return -EINVAL;
    if (capture->outstanding)
        return -EBUSY;
    bytes = iio_buffer_refill(capture->buffer);
    if (bytes < 0)
        return (int)bytes;
    block->raw = iio_buffer_start(capture->buffer);
    block->raw_bytes = (size_t)bytes;
    if (!block->raw || block->raw_bytes != capture->raw_bytes)
        return -EIO;
    if (++capture->token_generation == 0)
        ++capture->token_generation;
    block->token = capture->token_generation;
    capture->outstanding = true;
    return 0;
}

static int local_capture_release(void *unused, void *opaque, uintptr_t token)
{
    struct local_iio_capture *capture = opaque;

    (void)unused;
    if (!capture || !capture->outstanding || token != capture->token_generation)
        return -EINVAL;
    capture->outstanding = false;
    return 0;
}

static int local_capture_cancel(void *unused, void *opaque)
{
    struct local_iio_capture *capture = opaque;

    (void)unused;
    if (!capture || !capture->buffer)
        return -EINVAL;
    iio_buffer_cancel(capture->buffer);
    return 0;
}

static int local_capture_close(void *unused, void *opaque)
{
    struct local_iio_capture *capture = opaque;

    (void)unused;
    if (!capture)
        return -EINVAL;
    iio_buffer_destroy(capture->buffer);
    iio_context_destroy(capture->context);
    free(capture);
    return 0;
}

static int local_counter_open(void)
{
    int saved, fd = open("/dev/tandem-agc-events", O_RDWR | O_CLOEXEC);

    if (fd < 0)
        return -errno;
    if (flock(fd, LOCK_EX | LOCK_NB)) {
        saved = errno;
        close(fd);
        return -saved;
    }
    return fd;
}

static int local_counter_close(int fd)
{
    int saved = 0;

    if (fd < 0)
        return -EINVAL;
    if (flock(fd, LOCK_UN))
        saved = errno;
    if (close(fd) && !saved)
        saved = errno;
    return saved ? -saved : 0;
}

static int local_ioctl(int fd, unsigned long request, void *argument)
{
    int ret;

    do {
        ret = ioctl(fd, request, argument);
    } while (ret < 0 && errno == EINTR);
    return ret;
}

const struct leo_local_provider_ops *leo_local_iio_provider(void)
{
    static const struct leo_local_provider_ops provider = {
        .context = NULL,
        .capture_open = local_capture_open,
        .capture_acquire = local_capture_acquire,
        .capture_cancel = local_capture_cancel,
        .capture_release = local_capture_release,
        .capture_close = local_capture_close,
        .counter_open = local_counter_open,
        .counter_close = local_counter_close,
        .ioctl_call = local_ioctl,
    };

    return &provider;
}
