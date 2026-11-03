#include "usb_source.h"

#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

struct leo_usb_source {
    leo_usb_config config;
    leo_usb_provider_ops provider;
    leo_usb_capabilities capabilities;
    void *capture;
    uintptr_t provider_token;
    uint64_t stream_ordinal;
    uint64_t expected_counter;
    uint64_t previous_time_ns;
    uint64_t buffer_sequence;
    uint64_t lease_token;
    int have_counter;
    int have_time;
    int leased;
    int faulted;
};

static int valid_provider(const leo_usb_provider_ops *p) {
    return p && p->abi_version == LEO_USB_SOURCE_ABI_VERSION && p->probe &&
        p->open_exclusive && p->capture_acquire && p->capture_cancel &&
        p->capture_release && p->capture_close;
}

static int range_contains(uint64_t low, uint64_t high, uint64_t value) {
    return low <= high && value >= low && value <= high;
}

static int valid_capabilities(const leo_usb_capabilities *c) {
    const uint32_t known = LEO_USB_CAP_EXCLUSIVE_OPEN | LEO_USB_CAP_CANCEL |
        LEO_USB_CAP_OVERFLOW_REPORTING | LEO_USB_CAP_RETUNE |
        LEO_USB_CAP_SIMULTANEOUS_RX | LEO_USB_CAP_COHERENT_RX;
    return c && c->abi_version == LEO_USB_SOURCE_ABI_VERSION &&
        !(c->flags & ~known) && c->max_receivers >= 1 &&
        c->max_receivers <= 2 && c->max_samples_per_block &&
        c->minimum_sample_rate_hz && c->minimum_bandwidth_hz &&
        c->minimum_frequency_hz &&
        (!(c->flags & LEO_USB_CAP_COHERENT_RX) ||
          (c->flags & LEO_USB_CAP_SIMULTANEOUS_RX)) &&
        c->counter_authority != LEO_USB_COUNTER_SOFTWARE_DELIVERED &&
        c->counter_authority <= LEO_USB_COUNTER_PROVIDER_EXACT &&
        c->time_authority <= LEO_USB_TIME_DEVICE &&
        (c->time_authority != LEO_USB_TIME_NONE ||
         c->minimum_time_uncertainty_ns == 0) &&
        range_contains(c->minimum_sample_rate_hz,
            c->maximum_sample_rate_hz, c->minimum_sample_rate_hz) &&
        range_contains(c->minimum_bandwidth_hz,
            c->maximum_bandwidth_hz, c->minimum_bandwidth_hz) &&
        range_contains(c->minimum_frequency_hz,
            c->maximum_frequency_hz, c->minimum_frequency_hz);
}

int leo_usb_source_probe(const char *selector,
    const leo_usb_provider_ops *provider, leo_usb_capabilities *capabilities) {
    int status;
    if (!selector || !*selector || !valid_provider(provider) || !capabilities)
        return -EINVAL;
    memset(capabilities, 0, sizeof(*capabilities));
    status = provider->probe(provider->context, selector, capabilities);
    if (status) return status;
    return valid_capabilities(capabilities) ? 0 : -EPROTO;
}

static int validate_config(const leo_usb_config *q,
    const leo_usb_capabilities *c, const leo_usb_provider_ops *p) {
    if (!q || q->abi_version != LEO_USB_SOURCE_ABI_VERSION ||
        !q->selector || !*q->selector || !q->sample_rate_hz ||
        !q->analog_bandwidth_hz || !q->samples_per_block ||
        !q->receiver_count || q->receiver_count > 2 ||
        !q->center_frequency_hz ||
        q->require_exact_counter > 1 || q->require_device_time > 1)
        return -EINVAL;
    if (!(c->sample_format_mask & LEO_USB_SAMPLE_FORMAT_CI16) ||
        !(c->flags & LEO_USB_CAP_EXCLUSIVE_OPEN) ||
        !(c->flags & LEO_USB_CAP_CANCEL)) return -ENOTSUP;
    if (q->receiver_count > c->max_receivers ||
        q->samples_per_block > c->max_samples_per_block ||
        !range_contains(c->minimum_sample_rate_hz,c->maximum_sample_rate_hz,
            q->sample_rate_hz) ||
        !range_contains(c->minimum_bandwidth_hz,c->maximum_bandwidth_hz,
            q->analog_bandwidth_hz) ||
        !range_contains(c->minimum_frequency_hz,c->maximum_frequency_hz,
            q->center_frequency_hz)) return -ERANGE;
    if (q->receiver_count == 2 &&
        ((c->flags & (LEO_USB_CAP_SIMULTANEOUS_RX|LEO_USB_CAP_COHERENT_RX)) !=
         (LEO_USB_CAP_SIMULTANEOUS_RX|LEO_USB_CAP_COHERENT_RX)))
        return -ENOTSUP;
    if (q->require_exact_counter &&
        c->counter_authority != LEO_USB_COUNTER_PROVIDER_EXACT)
        return -ENOTSUP;
    if (q->require_device_time &&
        (c->time_authority != LEO_USB_TIME_DEVICE ||
         c->minimum_time_uncertainty_ns > q->maximum_time_uncertainty_ns))
        return -ENOTSUP;
    if ((c->flags & LEO_USB_CAP_RETUNE) && !p->retune) return -EPROTO;
    return 0;
}

int leo_usb_source_open(const leo_usb_config *config,
    const leo_usb_provider_ops *provider, leo_usb_source **out) {
    leo_usb_capabilities capabilities;
    leo_usb_source *source;
    int status;
    if (!out) return -EINVAL;
    *out = NULL;
    if (!valid_provider(provider)) return -EINVAL;
    status = leo_usb_source_probe(config ? config->selector : NULL, provider,
        &capabilities);
    if (status) return status;
    status = validate_config(config, &capabilities, provider);
    if (status) return status;
    source = (leo_usb_source *)calloc(1, sizeof(*source));
    if (!source) return -ENOMEM;
    source->config = *config;
    source->provider = *provider;
    source->capabilities = capabilities;
    status = source->provider.open_exclusive(source->provider.context, config,
        &source->capture);
    if (status || !source->capture) {
        if (source->capture)
            (void)source->provider.capture_close(source->provider.context,
                source->capture);
        free(source);
        return status ? status : -EPROTO;
    }
    *out = source;
    return 0;
}

static int block_bytes(uint32_t samples, uint32_t receivers, size_t *bytes) {
    size_t elements;
    if (!samples || !receivers || receivers > 2 ||
        samples > SIZE_MAX / (sizeof(int16_t) * 2u * receivers))
        return -EPROTO;
    elements = (size_t)samples * receivers * 2u;
    *bytes = elements * sizeof(int16_t);
    return 0;
}

static int fail_acquire(leo_usb_source *s, uintptr_t token, int error) {
    int release_status = s->provider.capture_release(s->provider.context,
        s->capture, token);
    s->faulted = 1;
    return error ? error : (release_status ? release_status : -EPROTO);
}

int leo_usb_source_next(leo_usb_source *s, leo_usb_block *out) {
    leo_usb_provider_block raw;
    size_t expected_bytes;
    uint64_t end;
    uint64_t missing = 0;
    uint32_t authority;
    int status;
    if (!s || !out) return -EINVAL;
    memset(out, 0, sizeof(*out));
    if (s->faulted) return -EIO;
    if (s->leased) return -EBUSY;
    memset(&raw, 0, sizeof(raw));
    status = s->provider.capture_acquire(s->provider.context,s->capture,&raw);
    if (status) return status;
    status = block_bytes(raw.samples_per_receiver,raw.receiver_count,
        &expected_bytes);
    if (status || !raw.ci16 || raw.iq_bytes != expected_bytes ||
        raw.samples_per_receiver > s->capabilities.max_samples_per_block ||
        raw.receiver_count != s->config.receiver_count ||
        raw.counter_authority == LEO_USB_COUNTER_SOFTWARE_DELIVERED ||
        raw.counter_authority != s->capabilities.counter_authority ||
        (raw.time_authority != LEO_USB_TIME_NONE &&
            raw.time_authority != s->capabilities.time_authority) ||
        (raw.time_authority == LEO_USB_TIME_NONE &&
            (raw.first_time_ns || raw.time_uncertainty_ns)) ||
        (raw.time_authority != LEO_USB_TIME_NONE &&
            raw.time_uncertainty_ns <
                s->capabilities.minimum_time_uncertainty_ns) ||
        (raw.flags & ~(LEO_USB_BLOCK_OVERFLOW_BEFORE|
            LEO_USB_BLOCK_DISCONTINUITY)))
        return fail_acquire(s,raw.token,status ? status : -EPROTO);
    if ((raw.flags & LEO_USB_BLOCK_OVERFLOW_BEFORE) &&
        !(s->capabilities.flags & LEO_USB_CAP_OVERFLOW_REPORTING))
        return fail_acquire(s,raw.token,-EPROTO);
    authority = raw.counter_authority;
    if (authority == LEO_USB_COUNTER_NONE ||
        authority == LEO_USB_COUNTER_SOFTWARE_DELIVERED) {
        authority = LEO_USB_COUNTER_SOFTWARE_DELIVERED;
        raw.first_counter = s->stream_ordinal;
    }
    if (s->config.require_exact_counter &&
        authority != LEO_USB_COUNTER_PROVIDER_EXACT)
        return fail_acquire(s,raw.token,-EPROTO);
    if (raw.samples_per_receiver > UINT64_MAX - raw.first_counter)
        return fail_acquire(s,raw.token,-EOVERFLOW);
    end = raw.first_counter + raw.samples_per_receiver;
    if (authority == LEO_USB_COUNTER_PROVIDER_EXACT) {
        if (s->have_counter && raw.first_counter < s->expected_counter)
            return fail_acquire(s,raw.token,-EPROTO);
        if (s->have_counter) {
            missing = raw.first_counter-s->expected_counter;
            raw.flags |= LEO_USB_BLOCK_GAP_EXACT;
        }
        s->expected_counter=end;
        s->have_counter=1;
        if (missing) raw.flags |= LEO_USB_BLOCK_DISCONTINUITY;
        if (raw.flags & LEO_USB_BLOCK_OVERFLOW_BEFORE)
            raw.flags |= LEO_USB_BLOCK_DISCONTINUITY;
    } else if (authority == LEO_USB_COUNTER_PROVIDER_ESTIMATED) {
        if (s->have_counter && raw.first_counter < s->expected_counter)
            return fail_acquire(s,raw.token,-EPROTO);
        if (s->have_counter && raw.first_counter != s->expected_counter)
            raw.flags |= LEO_USB_BLOCK_DISCONTINUITY;
        s->expected_counter=end;
        s->have_counter=1;
    }
    if (s->config.require_device_time &&
        (raw.time_authority != LEO_USB_TIME_DEVICE ||
         raw.time_uncertainty_ns > s->config.maximum_time_uncertainty_ns))
        return fail_acquire(s,raw.token,-EPROTO);
    if (raw.time_authority != LEO_USB_TIME_NONE) {
        if (s->have_time && raw.first_time_ns < s->previous_time_ns)
            return fail_acquire(s,raw.token,-EPROTO);
        s->previous_time_ns=raw.first_time_ns;
        s->have_time=1;
    }
    if (raw.samples_per_receiver > UINT64_MAX-s->stream_ordinal)
        return fail_acquire(s,raw.token,-EOVERFLOW);
    out->ci16=raw.ci16;
    out->iq_bytes=raw.iq_bytes;
    out->samples_per_receiver=raw.samples_per_receiver;
    out->receiver_count=raw.receiver_count;
    out->flags=raw.flags;
    out->counter_authority=authority;
    out->time_authority=raw.time_authority;
    out->stream_ordinal=s->stream_ordinal;
    out->first_counter=raw.first_counter;
    out->first_time_ns=raw.first_time_ns;
    out->time_uncertainty_ns=raw.time_uncertainty_ns;
    out->missing_samples_before=missing;
    out->buffer_sequence=++s->buffer_sequence;
    out->lease_token=++s->lease_token;
    if (!out->lease_token) out->lease_token=++s->lease_token;
    s->stream_ordinal+=raw.samples_per_receiver;
    s->provider_token=raw.token;
    s->leased=1;
    return 0;
}

int leo_usb_source_release(leo_usb_source *s, leo_usb_block *block) {
    int status;
    if (!s || !block) return -EINVAL;
    if (!s->leased || block->lease_token != s->lease_token) return -EINVAL;
    status=s->provider.capture_release(s->provider.context,s->capture,
        s->provider_token);
    s->leased=0;
    s->provider_token=0;
    memset(block,0,sizeof(*block));
    if (status) s->faulted=1;
    return status;
}

int leo_usb_source_retune(leo_usb_source *s, uint64_t frequency_hz,
    leo_usb_provider_retune *receipt) {
    uint64_t delta;
    int status;
    if (!s || !receipt || !frequency_hz) return -EINVAL;
    memset(receipt,0,sizeof(*receipt));
    if (s->faulted) return -EIO;
    if (s->leased) return -EBUSY;
    if (!(s->capabilities.flags & LEO_USB_CAP_RETUNE) || !s->provider.retune)
        return -ENOTSUP;
    if (!range_contains(s->capabilities.minimum_frequency_hz,
        s->capabilities.maximum_frequency_hz,frequency_hz)) return -ERANGE;
    status=s->provider.retune(s->provider.context,s->capture,frequency_hz,receipt);
    if (status) { s->faulted=1; return status; }
    if (!receipt->actual_frequency_hz ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_COUNTER) &&
            receipt->counter_authority!=s->capabilities.counter_authority) ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_TIME) &&
            receipt->time_authority!=s->capabilities.time_authority) ||
        (receipt->flags & ~(LEO_USB_RETUNE_VALID_COUNTER|
            LEO_USB_RETUNE_VALID_TIME)) ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_COUNTER) &&
            receipt->counter_authority==LEO_USB_COUNTER_NONE) ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_TIME) &&
            (receipt->time_authority==LEO_USB_TIME_NONE ||
             receipt->time_uncertainty_ns<
                s->capabilities.minimum_time_uncertainty_ns)) ||
        (!(receipt->flags & LEO_USB_RETUNE_VALID_COUNTER) &&
            (receipt->counter_authority!=LEO_USB_COUNTER_NONE ||
             receipt->valid_counter)) ||
        (!(receipt->flags & LEO_USB_RETUNE_VALID_TIME) &&
            (receipt->time_authority!=LEO_USB_TIME_NONE ||
             receipt->valid_time_ns || receipt->time_uncertainty_ns)) ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_COUNTER) &&
            receipt->counter_authority==LEO_USB_COUNTER_PROVIDER_EXACT &&
            s->have_counter && receipt->valid_counter<s->expected_counter) ||
        ((receipt->flags & LEO_USB_RETUNE_VALID_TIME) && s->have_time &&
            receipt->valid_time_ns<s->previous_time_ns)) {
        s->faulted=1;
        return -EPROTO;
    }
    delta=receipt->actual_frequency_hz>frequency_hz ?
        receipt->actual_frequency_hz-frequency_hz :
        frequency_hz-receipt->actual_frequency_hz;
    if (delta>s->config.maximum_frequency_error_hz) {
        s->faulted=1;
        return -ERANGE;
    }
    return 0;
}

int leo_usb_source_cancel(leo_usb_source *s) {
    if (!s) return -EINVAL;
    return s->provider.capture_cancel(s->provider.context,s->capture);
}

int leo_usb_source_close(leo_usb_source *s) {
    int status=0, current;
    if (!s) return -EINVAL;
    if (s->leased) {
        current=s->provider.capture_release(s->provider.context,s->capture,
            s->provider_token);
        if (current) status=current;
    }
    current=s->provider.capture_close(s->provider.context,s->capture);
    if (!status && current) status=current;
    free(s);
    return status;
}
